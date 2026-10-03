import os
import re
import time
import threading
import collections
from collections import OrderedDict
import concurrent.futures
from urllib.parse import urlparse

try:
    from qt.core import (
        Qt, QThread, pyqtSignal, QTimer, QPixmap
    )
except ImportError:
    pass

try:
    from calibre_plugins.libgen_store.config import prefs, get_mirrors, get_active_backend, BACKENDS
    from calibre_plugins.libgen_store.scraper import LibgenScraper, LibgenBook, get_scraper
except ImportError:
    from config import prefs, get_mirrors, get_active_backend, BACKENDS
    from scraper import LibgenScraper, LibgenBook, get_scraper

# --- END IMPORTS ---

class SearchWorker(QThread):
    finished_signal = pyqtSignal(list, str)   # books, mirror_used
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, str, int, int)  # current_idx, total_mirrors, mirror_url, found_count, target_count
    partial_results_signal = pyqtSignal(list, str)  # books_so_far, mirror_url

    def __init__(self, query, search_field, category, selected_mirror, language, fmt, filter_mode, max_results=5, unique_results=True, parent=None):
        super().__init__(parent)
        self.query = query
        self.search_field = search_field
        self.category = category
        self.selected_mirror = selected_mirror
        self.language = language
        self.fmt = fmt
        self.filter_mode = filter_mode
        self.max_results = max_results
        self.unique_results = unique_results
        self._is_aborted = False
        self._current_mirror = ""

    def abort(self):
        self._is_aborted = True

    def run(self):
        try:
            mirrors = get_mirrors()
            timeout = int(prefs.get("search_timeout", 8))

            scraper = get_scraper(mirrors=mirrors, timeout=timeout)

            def on_progress(idx, total, mirror, found_count=0, target_count=0):
                self._current_mirror = mirror
                self.progress_signal.emit(idx, total, mirror, found_count, target_count)

            def on_partial_results(books_so_far, mirror):
                if self._is_aborted:
                    return
                self._current_mirror = mirror
                self.partial_results_signal.emit(books_so_far, mirror)

            books = scraper.search(
                query=self.query,
                search_field=self.search_field,
                category=self.category,
                selected_mirror=self.selected_mirror,
                max_results=self.max_results,
                preferred_language=self.language,
                preferred_format=self.fmt,
                filter_mode=self.filter_mode,
                unique_results=self.unique_results,
                progress_callback=on_progress,
                partial_results_callback=on_partial_results,
                abort_check=lambda: self._is_aborted,
            )
            if self._is_aborted:
                return
            self.finished_signal.emit(books, self._current_mirror)
        except Exception as e:
            if not self._is_aborted:
                self.error_signal.emit(str(e))


class SearchQueueWorker(QThread):
    progress_signal = pyqtSignal(int, int, str, str)  # current_idx, total_records, label, status_msg
    record_finished_signal = pyqtSignal(dict, list)   # record_info, matched_books
    finished_signal = pyqtSignal(list, int, int)       # all_results, matched_records_cnt, failed_records_cnt

    def __init__(self, records, mirrors, selected_mirror="Auto", timeout=20, language=None, fmt="Any", filter_mode="Prioritize", unique_results=True, parent=None):
        super().__init__(parent)
        self.records = list(records)
        self.mirrors = list(mirrors)
        self.selected_mirror = selected_mirror
        self.timeout = timeout
        self.language = language
        self.fmt = fmt
        self.filter_mode = filter_mode
        self.unique_results = unique_results
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def run(self):
        all_results = []
        matched_records = 0
        failed_records = 0
        top_mirrors = [m for m in self.mirrors[:5] if m]
        if self.selected_mirror and self.selected_mirror != "Auto":
            top_mirrors = [self.selected_mirror]
        if not top_mirrors:
            top_mirrors = ["Auto"]
        results_lock = threading.Lock()
        completed = [0]

        # Fast first-pass timeout (5s); retry pass timeout (10s)
        fast_timeout = min(5, max(3, self.timeout // 2))
        retry_timeout = min(10, max(5, self.timeout))

        # Two passes:
        # Pass 1: Quick attempt across all records. Any that timeout or fail are deferred.
        # Pass 2: Deferred entries are retried at the very end of the list.
        pending_queue = collections.deque(list(enumerate(self.records, 1)))
        deferred_records = []
        total = len(self.records)

        def search_record(record_index, rec, timeout_sec, is_deferred=False):
            if self._is_aborted:
                return False, rec, []

            title = rec.get("title", "")
            author = rec.get("author", "")
            isbn = rec.get("isbn", "")
            assigned_mirror = top_mirrors[(record_index - 1) % len(top_mirrors)]
            mirror_order = [assigned_mirror] + [m for m in self.mirrors if m.rstrip("/") != assigned_mirror.rstrip("/")]
            scraper = LibgenScraper(mirrors=mirror_order, timeout=timeout_sec)

            label = f"{title} - {author}".strip(" -") or isbn or f"Record #{record_index}"
            host = urlparse(assigned_mirror).netloc or assigned_mirror
            tag = " [Deferred Retry]" if is_deferred else ""
            self.progress_signal.emit(
                completed[0] + 1,
                total,
                label,
                f"Lane {((record_index - 1) % len(top_mirrors)) + 1}: querying {host} for '{label}'{tag} (max 1)...",
            )

            results = []

            # 1. Try ISBN if available (strictly max_results = 1 for instant exit)
            if isbn:
                try:
                    results = scraper.search(
                        query=isbn,
                        search_field="i",
                        selected_mirror=assigned_mirror,
                        max_results=1,
                        preferred_language=self.language,
                        preferred_format=self.fmt,
                        filter_mode=self.filter_mode,
                        unique_results=self.unique_results,
                        abort_check=lambda: self._is_aborted,
                    )
                except Exception:
                    results = []

            # 2. Fallback to Title + Author if no ISBN results (strictly max_results = 1)
            if not results and (title or author):
                q = f"{title} {author}".strip()
                try:
                    results = scraper.search(
                        query=q,
                        search_field="",
                        selected_mirror=assigned_mirror,
                        max_results=1,
                        preferred_language=self.language,
                        preferred_format=self.fmt,
                        filter_mode=self.filter_mode,
                        unique_results=self.unique_results,
                        abort_check=lambda: self._is_aborted,
                    )
                except Exception:
                    results = []

            # Ensure hard limit of strictly max 1 result per record
            results = results[:1] if results else []
            return bool(results), rec, results

        concurrency = min(5, max(2, len(self.records)))

        # Pass 1: Fast queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(search_record, idx, rec, fast_timeout, False): (idx, rec)
                for idx, rec in pending_queue
            }
            for fut in concurrent.futures.as_completed(futures):
                if self._is_aborted:
                    break
                idx, rec = futures[fut]
                try:
                    has_results, rec, results = fut.result()
                except Exception:
                    has_results, rec, results = False, rec, []

                title = rec.get("title", "")
                author = rec.get("author", "")
                isbn = rec.get("isbn", "")
                label = f"{title} - {author}".strip(" -") or isbn or f"Record #{idx}"

                if has_results:
                    with results_lock:
                        completed[0] += 1
                        done = completed[0]
                        matched_records += 1
                        for b in results:
                            setattr(b, "calibre_source", label)
                            if not any(getattr(existing, "detail_url", None) == b.detail_url for existing in all_results):
                                all_results.append(b)
                    self.progress_signal.emit(done, total, label, f"✓ Found {len(results)} match(es)")
                    self.record_finished_signal.emit(rec, results)
                else:
                    # Difficult entry: defer to end of the list
                    deferred_records.append((idx, rec))
                    self.progress_signal.emit(completed[0], total, label, f"↷ Deferring '{label[:30]}' to end of queue...")

        # Pass 2: Retry deferred entries at the end of the list with broader timeout
        if deferred_records and not self._is_aborted:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(deferred_records))) as pool:
                futures = {
                    pool.submit(search_record, idx, rec, retry_timeout, True): (idx, rec)
                    for idx, rec in deferred_records
                }
                for fut in concurrent.futures.as_completed(futures):
                    if self._is_aborted:
                        break
                    idx, rec = futures[fut]
                    try:
                        has_results, rec, results = fut.result()
                    except Exception:
                        has_results, rec, results = False, rec, []

                    with results_lock:
                        completed[0] += 1
                        done = completed[0]

                    title = rec.get("title", "")
                    author = rec.get("author", "")
                    isbn = rec.get("isbn", "")
                    label = f"{title} - {author}".strip(" -") or isbn or f"Record #{done}"

                    if has_results:
                        with results_lock:
                            matched_records += 1
                            for b in results:
                                setattr(b, "calibre_source", label)
                                if not any(getattr(existing, "detail_url", None) == b.detail_url for existing in all_results):
                                    all_results.append(b)
                        self.progress_signal.emit(done, total, label, f"✓ Found {len(results)} match(es) (deferred)")
                        self.record_finished_signal.emit(rec, results)
                    else:
                        failed_records += 1
                        query_fallback = isbn or f"{title} {author}".strip()
                        if query_fallback:
                            add_pending_search(query_fallback)
                        self.progress_signal.emit(done, total, label, "✗ 0 matches (saved to Pending)")
                        self.record_finished_signal.emit(rec, [])

        self.finished_signal.emit(all_results, matched_records, failed_records)


class MirrorHealthWorker(QThread):
    mirror_tested = pyqtSignal(str, bool, int, float, str, str)  # url, is_ok, latency_ms, kb_s, speed_str, status_msg
    all_tested = pyqtSignal()
    mirrors_discovered = pyqtSignal(list)

    def __init__(self, mirrors, parent=None):
        super().__init__(parent)
        self.mirrors = mirrors

    def run(self):
        scraper = LibgenScraper(timeout=8)
        
        # 1. Fetch live mirrors from open-slum.org
        live_mirrors = scraper.fetch_live_mirrors()
        if live_mirrors:
            self.mirrors_discovered.emit(live_mirrors)
            for m in live_mirrors:
                if m not in self.mirrors:
                    self.mirrors.append(m)

        def _ping(mirror):
            return mirror, scraper.ping_mirror(mirror, timeout=8)
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(self.mirrors))) as pool:
            futures = [pool.submit(_ping, m) for m in self.mirrors]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    mirror, (is_ok, ms, kb_s, speed_str, msg) = fut.result()
                    self.mirror_tested.emit(mirror, is_ok, ms, kb_s, speed_str, msg)
                except Exception:
                    pass
        
        self.all_tested.emit()

class CoverFetchWorker(QThread):
    cover_fetched = pyqtSignal(bytes, str)
    cover_failed = pyqtSignal(str)

    def __init__(self, book_or_detail_url, parent=None):
        super().__init__(parent)
        if isinstance(book_or_detail_url, str):
            self.detail_url = book_or_detail_url
            self.book = None
        else:
            self.book = book_or_detail_url
            self.detail_url = getattr(self.book, "detail_url", "")
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def run(self):
        try:
            from calibre_plugins.libgen_store.scraper import LibgenScraper
        except Exception:
            try:
                from scraper import LibgenScraper
            except Exception:
                if not self._is_aborted:
                    self.cover_failed.emit(self.detail_url)
                return

        try:
            scraper = LibgenScraper(timeout=5)
            cover_url = getattr(self.book, "cover_url", "") if self.book else ""

            # 1. Resolve cover URL from detail page if not cached
            if not cover_url and self.detail_url:
                if self._is_aborted:
                    return
                _, cover_url = scraper.resolve_details(self.detail_url, timeout=4)

                if not cover_url:
                    fallbacks = scraper.get_fallback_detail_urls(self.detail_url)
                    for fb in fallbacks:
                        if self._is_aborted:
                            return
                        if fb == self.detail_url:
                            continue
                        _, cover_url = scraper.resolve_details(fb, timeout=3)
                        if cover_url:
                            break

                if cover_url and self.book:
                    self.book.cover_url = cover_url

            if self._is_aborted or not cover_url:
                self.cover_failed.emit(self.detail_url)
                return

            # 2. Candidate cover image URLs: libgen.li is primary reliable image host
            img_candidates = []
            parsed = urlparse(cover_url)
            if any(ext in parsed.netloc for ext in [".la", ".gl", ".vg", ".bz"]):
                li_url = cover_url.replace(parsed.netloc, "libgen.li")
                img_candidates.append(li_url)
            if cover_url not in img_candidates:
                img_candidates.append(cover_url)

            b = scraper._get_browser()
            data = None
            for u in img_candidates:
                if self._is_aborted:
                    return
                try:
                    u_parsed = urlparse(u)
                    referer = f"{u_parsed.scheme}://{u_parsed.netloc}/"
                    b.addheaders = [("User-Agent", scraper.USER_AGENT), ("Referer", referer)]
                    resp = b.open(u, timeout=4)
                    chunk = resp.read()
                    if chunk and len(chunk) > 300 and not chunk.startswith(b"<!DOCTYPE") and not chunk.startswith(b"<html"):
                        data = chunk
                        break
                except Exception:
                    continue

            if self._is_aborted:
                return

            if data:
                self.cover_fetched.emit(data, self.detail_url)
                return

            self.cover_failed.emit(self.detail_url)
        except Exception:
            if not self._is_aborted:
                self.cover_failed.emit(self.detail_url)

class LiveMirrorWorker(QThread):
    mirrors_discovered = pyqtSignal(list)
    def run(self):
        try:
            from calibre_plugins.libgen_store.scraper import LibgenScraper
            mirrors = LibgenScraper.fetch_live_mirrors()
            self.mirrors_discovered.emit(mirrors)
        except Exception:
            self.mirrors_discovered.emit([])

class BulkDownloadWorker(QThread):
    item_status = pyqtSignal(int, str)             # index, status text
    item_progress = pyqtSignal(int, int, int, float)  # index, bytes_read, total_bytes, speed_kb
    log_message = pyqtSignal(str)                  # timestamped scrolling log line
    link_trying = pyqtSignal(int, str, str)        # index, url, stage ("resolving" or "streaming")
    all_done = pyqtSignal(list, int, bool)         # downloaded_items, fail_count, is_aborted

    def __init__(self, items, auto_retry=False, fast_mode=False, download_dir=None, concurrent_files=1, parent=None):
        super().__init__(parent)
        self.items = items
        self.auto_retry = auto_retry
        self.fast_mode = fast_mode
        self.download_dir = download_dir
        self.concurrent_files = max(1, min(4, int(concurrent_files or 1)))
        self._is_aborted = False


    def abort(self):
        self._is_aborted = True

    def run(self):
        mirrors = get_mirrors()
        timeout = int(prefs.get("timeout", 20))
        scraper = get_scraper(mirrors=mirrors, timeout=timeout)

        download_dir = self.download_dir or prefs.get("download_directory", "")
        if not download_dir:
            download_dir = os.path.join(os.path.expanduser("~"), "Downloads", "LibGen Downloader")
        download_dir = os.path.abspath(os.path.expanduser(download_dir))
        os.makedirs(download_dir, exist_ok=True)
        try:
            downloaded_items = []
            fail_count = 0

            while not self._is_aborted:
                fail_count = 0
                any_processed = False

                pending_items = [(idx, i) for idx, i in enumerate(self.items) if i.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")]
                total_pending = len(pending_items)
                current_num = [0]
                dl_lock = threading.Lock()
                fail_count_ref = [0]

                def process_item(idx, item):
                    if self._is_aborted:
                        return

                    book = item["book"]
                    with dl_lock:
                        current_num[0] += 1
                        c_num = current_num[0]

                    ts = time.strftime('%H:%M:%S')
                    short_title = (book.title or "Unknown")[:45]
                    self.log_message.emit(f"[{ts}] [{c_num}/{total_pending}] Starting: \"{short_title}\"")
                    self.item_status.emit(idx, "Resolving mirror link...")

                    ext = (book.extension or "epub").lower()
                    safe_title = sanitize_filename(book.title or "Unknown")
                    safe_author = sanitize_filename(book.author or "Unknown")
                    base_dest_file = os.path.join(download_dir, f"{safe_title} - {safe_author}.{ext}")
                    dest_file = base_dest_file
                    suffix = 1
                    while os.path.exists(dest_file):
                        dest_file = os.path.join(download_dir, f"{safe_title} - {safe_author} ({suffix}).{ext}")
                        suffix += 1

                    def on_log(msg):
                        t_now = time.strftime('%H:%M:%S')
                        self.log_message.emit(f"[{t_now}] {msg}")

                    def on_progress(bytes_read, total, speed_kb=0.0):
                        self.item_progress.emit(idx, bytes_read, total, float(speed_kb))

                    def on_link(url, stage):
                        self.link_trying.emit(idx, url, stage)

                    try:
                        cur_backend = get_active_backend()
                        allow_br = (cur_backend == "dual" and prefs.get("bookracy_auto_retry_failed", True))
                        force_br = bool(item.get("force_bookracy", False))
                        dest_path, cover_url = scraper.resolve_and_download(
                            book.detail_url,
                            dest_file,
                            book_title=book.title,
                            book_author=book.author,
                            book_ext=book.extension,
                            log_callback=on_log,
                            progress_callback=on_progress,
                            link_callback=on_link,
                            abort_check=lambda: self._is_aborted,
                            fast_mode=self.fast_mode,
                            allow_bookracy=allow_br,
                            force_bookracy=force_br,
                        )
                        self.item_status.emit(idx, f"✓ Downloaded (Pending Review)|{dest_path}")
                        with dl_lock:
                            downloaded_items.append({
                                "index": idx,
                                "book": book,
                                "file_path": dest_path,
                            })
                    except Exception as e:
                        err_msg = str(e)
                        if "stopped by user" in err_msg.lower() or self._is_aborted:
                            if os.path.exists(dest_file):
                                try:
                                    os.remove(dest_file)
                                except Exception:
                                    pass
                            self.item_status.emit(idx, "Stopped")
                            on_log(f"⚠ Stopped downloading \"{short_title}\" by user request.")
                            return
                        self.item_status.emit(idx, f"Failed: {err_msg[:40]}")
                        on_log(f"✗ Failed to download \"{short_title}\": {err_msg}")
                        with dl_lock:
                            fail_count_ref[0] += 1

                with concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrent_files) as pool:
                    futures = [pool.submit(process_item, idx, item) for idx, item in pending_items]
                    for fut in concurrent.futures.as_completed(futures):
                        pass

            
                fail_count = fail_count_ref[0]

                if not self.auto_retry or fail_count == 0 or self._is_aborted:
                    break
            
                if self.auto_retry and fail_count > 0:
                    t_now = time.strftime('%H:%M:%S')
                    self.log_message.emit(f"[{t_now}] ↻ Auto-retry enabled. Retrying {fail_count} failed item(s) in 3 seconds...")
                    for _ in range(30):
                        if self._is_aborted:
                            break
                        time.sleep(0.1)

            self.all_done.emit(downloaded_items, fail_count, bool(self._is_aborted))
        finally:
            pass



