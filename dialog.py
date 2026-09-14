#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Dedicated UI dialog for LibGen Downloader with search, field selection,
mirror selection/health checks, and queue download manager directly inside Calibre.
"""

import os
import re
import time
import threading
import collections
from collections import OrderedDict
import concurrent.futures
from urllib.parse import urlparse

from qt.core import (
    Qt,
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QProgressBar,
    QMessageBox,
    QThread,
    pyqtSignal,
    QWidget,
    QColor,
    QGroupBox,
    QMenu,
    QShortcut,
    QKeySequence,
    QPlainTextEdit,
    QTimer,
    QCheckBox,
    QSpinBox,
    QStandardItem,
    QStandardItemModel,
    QCompleter,
    QFormLayout,
    QByteArray,
    QRadioButton,
    QButtonGroup,
    QFileDialog,
)

PROGRESS_BAR_STYLE = (
    "QProgressBar { border: 1px solid palette(mid); border-radius: 4px; "
    "background: palette(base); text-align: center; font-size: 11px; "
    "font-weight: 600; color: palette(text); } "
    "QProgressBar::chunk { background: palette(highlight); border-radius: 3px; }"
)

PRIMARY_BUTTON_STYLE = "font-weight: 600; padding: 5px 14px;"
DANGER_BUTTON_STYLE = "font-weight: 600; padding: 5px 14px;"
COMPACT_BUTTON_STYLE = "font-weight: 600; padding: 4px 10px;"
FILTER_BUTTON_STYLE = "padding: 3px 10px;"
FILTER_BUTTON_ACTIVE_STYLE = (
    "font-weight: 600; padding: 3px 10px; "
    "background: palette(highlight); color: palette(highlighted-text);"
)
PANEL_STYLE = (
    "background: palette(base); border: 1px solid palette(mid); "
    "border-radius: 5px; color: palette(text);"
)
MONO_PANEL_STYLE = (
    "background: palette(base); color: palette(text); font-family: monospace; "
    "font-size: 11px; padding: 6px; border: 1px solid palette(mid); border-radius: 4px;"
)

try:
    from calibre_plugins.libgen_store.progress_delegate import ProgressBarDelegate
except ImportError:
    from progress_delegate import ProgressBarDelegate


try:
    from calibre_plugins.libgen_store.config import (
        prefs,
        SUPPORTED_LANGUAGES,
        SUPPORTED_FORMATS,
        FILTER_MODES,
        SEARCH_FIELDS,
        CATEGORIES,
        get_mirrors,
        set_mirror_order,
        record_mirror_latency,
        add_custom_mirror,
        remove_custom_mirror,
        discard_mirrors,
        PLUGIN_VERSION_STR,
        get_fastest_cdns,
        append_search_history,
        get_search_history,
        get_search_history_filepath,
        append_download_history,
        get_download_history,
        clear_download_history,
        clear_all_history,
        cleanup_expired_history,
        get_pending_searches,
        add_pending_search,
        remove_pending_search,
        clear_pending_searches,
    )
    from calibre_plugins.libgen_store.scraper import LibgenScraper, LibgenBook
except (ImportError, ModuleNotFoundError):
    from config import (
        prefs,
        SUPPORTED_LANGUAGES,
        SUPPORTED_FORMATS,
        FILTER_MODES,
        SEARCH_FIELDS,
        CATEGORIES,
        get_mirrors,
        set_mirror_order,
        record_mirror_latency,
        add_custom_mirror,
        remove_custom_mirror,
        discard_mirrors,
        PLUGIN_VERSION_STR,
        get_fastest_cdns,
        append_search_history,
        get_search_history,
        get_search_history_filepath,
        append_download_history,
        get_download_history,
        clear_download_history,
        clear_all_history,
        cleanup_expired_history,
        get_pending_searches,
        add_pending_search,
        remove_pending_search,
        clear_pending_searches,
    )
    from scraper import LibgenScraper, LibgenBook

try:
    from calibre_plugins.libgen_store.hardcover import (
        fetch_user_shelves_and_lists,
        fetch_shelf_books,
    )
except ImportError:
    try:
        from hardcover import fetch_user_shelves_and_lists, fetch_shelf_books
    except ImportError:
        pass


def serialize_book(book):
    return {
        "id": getattr(book, "id", "") or "",
        "md5": getattr(book, "md5", "") or "",
        "title": getattr(book, "title", "") or "",
        "author": getattr(book, "author", "") or "",
        "publisher": getattr(book, "publisher", "") or "",
        "year": getattr(book, "year", "") or "",
        "language": getattr(book, "language", "") or "",
        "pages": getattr(book, "pages", "") or "",
        "size": getattr(book, "size", "") or "",
        "extension": getattr(book, "extension", "") or "",
        "detail_url": getattr(book, "detail_url", "") or "",
        "download_url": getattr(book, "download_url", "") or "",
        "cover_url": getattr(book, "cover_url", "") or "",
    }


def deserialize_book(d):
    b = LibgenBook()
    for k, v in d.items():
        setattr(b, k, v)
    return b


def sanitize_filename(name):
    """Clean filename of illegal filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:100]

class SizeTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        def _parse(s):
            if not s or s == "-": return 0.0
            s_upper = s.upper()
            try:
                val = float(''.join(c for c in s_upper if c.isdigit() or c == '.'))
                if "KB" in s_upper: return val * 1024
                if "MB" in s_upper: return val * 1024 * 1024
                if "GB" in s_upper: return val * 1024 * 1024 * 1024
                return val
            except:
                return 0.0
        return _parse(self.text()) < _parse(other.text())


class CheckableComboBox(QComboBox):
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(QStandardItemModel(self))
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view().pressed.connect(self.handle_item_pressed)

    def handle_item_pressed(self, index):
        item = self.model().itemFromIndex(index)
        if not item:
            return
        if item.text() == "Any":
            for r in range(self.model().rowCount()):
                it = self.model().item(r)
                if it:
                    it.setCheckState(Qt.CheckState.Checked if r == index.row() else Qt.CheckState.Unchecked)
        else:
            any_item = self.model().item(0)
            if any_item and any_item.text() == "Any":
                any_item.setCheckState(Qt.CheckState.Unchecked)
            new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(new_state)

            has_checked = any(
                self.model().item(r).checkState() == Qt.CheckState.Checked
                for r in range(self.model().rowCount())
                if self.model().item(r)
            )
            if not has_checked and any_item:
                any_item.setCheckState(Qt.CheckState.Checked)

        self.update_display_text()
        self.selection_changed.emit(self.checked_items())

    def add_checkable_items(self, items, checked_items=None):
        self.model().clear()
        checked_set = set(checked_items or ["Any"])
        if not checked_set or "Any" in checked_set:
            checked_set = {"Any"}
        for text in items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            is_chk = (text in checked_set)
            item.setCheckState(Qt.CheckState.Checked if is_chk else Qt.CheckState.Unchecked)
            self.model().appendRow(item)
        self.update_display_text()

    def checked_items(self):
        checked = []
        for r in range(self.model().rowCount()):
            it = self.model().item(r)
            if it and it.checkState() == Qt.CheckState.Checked:
                checked.append(it.text())
        if not checked:
            checked = ["Any"]
        return checked

    LANG_CODE_MAP = {
        "English": "EN",
        "Spanish": "ES",
        "French": "FR",
        "German": "DE",
        "Russian": "RU",
        "Italian": "IT",
        "Portuguese": "PT",
        "Chinese": "ZH",
        "Japanese": "JA",
        "Any": "Any",
    }

    def update_display_text(self):
        items = self.checked_items()
        if "Any" in items or not items:
            self.setEditText("Any")
            self.setToolTip("Filter by languages (Click to check multiple)")
        elif len(items) == 1:
            code = self.LANG_CODE_MAP.get(items[0], items[0][:3].upper())
            self.setEditText(code)
            self.setToolTip(f"Language: {items[0]}")
        else:
            short_codes = [self.LANG_CODE_MAP.get(i, i[:3].upper()) for i in items]
            self.setEditText(", ".join(short_codes))
            self.setToolTip(f"Languages: {', '.join(items)}")

    def hidePopup(self):
        super().hidePopup()
        self.update_display_text()


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

            scraper = LibgenScraper(mirrors=mirrors, timeout=timeout)

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

    def __init__(self, items, auto_retry=False, fast_mode=False, download_dir=None, parent=None):
        super().__init__(parent)
        self.items = items
        self.auto_retry = auto_retry
        self.fast_mode = fast_mode
        self.download_dir = download_dir
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def run(self):
        mirrors = get_mirrors()
        timeout = int(prefs.get("timeout", 20))
        scraper = LibgenScraper(mirrors=mirrors, timeout=timeout)

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
                        self.item_status.emit(idx, "Downloading...")
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

                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
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



class HistorySettingsDialog(QDialog):
    """Configuration dialog for search & download history limits and auto-retention."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("History & Retention Settings")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.save_history_checkbox = QCheckBox("Save search query history and enable autocomplete", self)
        self.save_history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
        form.addRow("Search History:", self.save_history_checkbox)

        self.max_search_spin = QSpinBox(self)
        self.max_search_spin.setRange(5, 1000)
        self.max_search_spin.setValue(int(prefs.get("max_search_history", 50)))
        form.addRow("Max Search Queries:", self.max_search_spin)

        self.max_dl_spin = QSpinBox(self)
        self.max_dl_spin.setRange(5, 1000)
        self.max_dl_spin.setValue(int(prefs.get("max_download_history", 50)))
        form.addRow("Max Download History:", self.max_dl_spin)

        self.retention_spin = QSpinBox(self)
        self.retention_spin.setRange(0, 365)
        self.retention_spin.setSuffix(" days")
        self.retention_spin.setSpecialValueText("Never (Keep indefinitely)")
        self.retention_spin.setValue(int(prefs.get("history_retention_days", 30)))
        self.retention_spin.setToolTip("Auto-clears search queries and download logs older than X days. Set to 0 to disable.")
        form.addRow("Clear History After:", self.retention_spin)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.clear_all_btn = QPushButton("Clear All History", self)
        self.clear_all_btn.clicked.connect(self.on_clear_all)
        btn_row.addWidget(self.clear_all_btn)
        btn_row.addStretch()

        self.save_btn = QPushButton("Save", self)
        self.save_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.save_btn.clicked.connect(self.on_save)
        btn_row.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

    def on_clear_all(self):
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all search query and download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_all_history("all")
            QMessageBox.information(self, "History Cleared", "Search and download history have been cleared.")

    def on_save(self):
        prefs["save_search_history"] = self.save_history_checkbox.isChecked()
        prefs["max_search_history"] = self.max_search_spin.value()
        prefs["max_download_history"] = self.max_dl_spin.value()
        prefs["history_retention_days"] = self.retention_spin.value()
        cleanup_expired_history()
        self.accept()


class HardcoverShelfDialog(QDialog):
    """Dialog to fetch user bookshelves/lists from Hardcover.app and populate the bulk download queue."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_dialog = parent
        self.setWindowTitle("Hardcover Shelf & List Downloader")
        saved_w = min(880, max(480, int(prefs.get("hardcover_dialog_width", 640))))
        saved_h = min(680, max(380, int(prefs.get("hardcover_dialog_height", 460))))
        self.resize(saved_w, saved_h)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(6)

        self.fetched_books = []
        self.shelves_data = []
        self._loading_combo = False

        # Top section: Token & Shelves
        top_group = QGroupBox("Hardcover Authentication & Shelf Selection")
        top_layout = QVBoxLayout(top_group)
        top_layout.setSpacing(6)

        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Token:"))
        self.token_edit = QLineEdit(self)
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setText(prefs.get("hardcover_token", ""))
        self.token_edit.setPlaceholderText("Hardcover API token")
        self.token_edit.setMaximumWidth(220)
        token_row.addWidget(self.token_edit)

        self.fetch_shelves_btn = QPushButton("Refresh Shelves", self)
        self.fetch_shelves_btn.setStyleSheet("font-weight: bold;")
        self.fetch_shelves_btn.clicked.connect(lambda: self.on_fetch_shelves(force_refresh=True))
        token_row.addWidget(self.fetch_shelves_btn)
        token_row.addStretch(1)
        top_layout.addLayout(token_row)

        shelf_row = QHBoxLayout()
        shelf_row.addWidget(QLabel("Shelf:"))
        self.shelf_combo = QComboBox(self)
        self.shelf_combo.addItem("Use Refresh Shelves to load...")
        self.shelf_combo.currentIndexChanged.connect(self.on_shelf_selected)
        self.shelf_combo.setMinimumWidth(180)
        shelf_row.addWidget(self.shelf_combo, stretch=1)

        self.load_books_btn = QPushButton("Refresh Books", self)
        self.load_books_btn.clicked.connect(lambda: self.on_load_books(force_refresh=True))
        shelf_row.addWidget(self.load_books_btn)
        top_layout.addLayout(shelf_row)

        # Matching mode
        match_group = QGroupBox("Queue Matching")
        match_layout = QHBoxLayout(match_group)
        match_layout.setSpacing(10)
        self.mode_btn_group = QButtonGroup(self)

        self.isbn_mode_radio = QRadioButton("ISBN only")
        self.isbn_mode_radio.setToolTip("Use ISBN column only to query LibGen")
        self.text_mode_radio = QRadioButton("Author + title")
        self.text_mode_radio.setToolTip("Search LibGen using book title and author")
        self.mode_btn_group.addButton(self.isbn_mode_radio)
        self.mode_btn_group.addButton(self.text_mode_radio)

        saved_mode = prefs.get("hardcover_match_mode", "ISBN Only")
        if saved_mode == "ISBN Only":
            self.isbn_mode_radio.setChecked(True)
        else:
            self.text_mode_radio.setChecked(True)

        self.isbn_mode_radio.toggled.connect(self.on_mode_changed)
        match_layout.addWidget(self.isbn_mode_radio)
        match_layout.addWidget(self.text_mode_radio)

        self.skip_library_checkbox = QCheckBox("Skip in-library books", self)
        self.skip_library_checkbox.setToolTip("Checks your Calibre database for matching ISBN or title to avoid duplicate searches")
        self.skip_library_checkbox.setChecked(bool(prefs.get("hardcover_skip_in_library", True)))
        self.skip_library_checkbox.stateChanged.connect(lambda v: prefs.__setitem__("hardcover_skip_in_library", bool(v)))
        match_layout.addWidget(self.skip_library_checkbox)
        match_layout.addStretch(1)

        top_layout.addWidget(match_group)

        self.layout.addWidget(top_group)

        # Books Table
        self.books_table = QTableWidget(self)
        self.books_table.setColumnCount(5)
        self.books_table.setHorizontalHeaderLabels([
            "Title", "Author", "ISBN", "Year", "Status"
        ])
        self.books_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.books_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.layout.addWidget(self.books_table)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All", self)
        self.select_all_btn.clicked.connect(self.select_all_books)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All", self)
        self.deselect_all_btn.clicked.connect(self.deselect_all_books)
        btn_row.addWidget(self.deselect_all_btn)

        self.select_first_btn = QPushButton("Select First N", self)
        self.select_first_btn.setToolTip("Select the top N books from the table based on queue limit")
        self.select_first_btn.clicked.connect(self.select_first_n_books)
        btn_row.addWidget(self.select_first_btn)

        btn_row.addStretch()

        btn_row.addWidget(QLabel("Max to queue:"))
        self.max_queue_spin = QSpinBox(self)
        self.max_queue_spin.setRange(0, 500)
        self.max_queue_spin.setValue(int(prefs.get("hardcover_max_queue_limit", 10)))
        self.max_queue_spin.setToolTip("Maximum number of books to query and queue (0 = all selected)")
        self.max_queue_spin.valueChanged.connect(lambda v: prefs.__setitem__("hardcover_max_queue_limit", v))
        btn_row.addWidget(self.max_queue_spin)

        self.queue_btn = QPushButton("▶ Add to Queue", self)
        self.queue_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.queue_btn.setToolTip("Add selected books to the main window's parallel Search Queue")
        self.queue_btn.clicked.connect(self.on_queue_selected)
        btn_row.addWidget(self.queue_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.close_btn)

        self.layout.addLayout(btn_row)

        self.restore_state()
        self.load_cached_shelves()

    def on_mode_changed(self):
        mode = "ISBN Only" if self.isbn_mode_radio.isChecked() else "Author & Title"
        prefs["hardcover_match_mode"] = mode

    def _hardcover_cache_key(self, token):
        import hashlib
        return hashlib.sha256((token or "").encode("utf-8")).hexdigest()[:16]

    def _books_cache_key(self, token, shelf_type, target_id):
        return f"{self._hardcover_cache_key(token)}:{shelf_type}:{target_id}"

    def _populate_shelves(self, data):
        self.shelves_data = []
        self._loading_combo = True
        self.shelf_combo.clear()

        for s in data.get("shelves", []):
            self.shelves_data.append(s)
            self.shelf_combo.addItem(f"📁 Shelf: {s['name']}", s)

        for l in data.get("lists", []):
            self.shelves_data.append(l)
            cnt = l.get("books_count", 0)
            self.shelf_combo.addItem(f"📋 List: {l['name']} ({cnt} books)", l)

        if not self.shelves_data:
            self.shelf_combo.addItem("No cached shelves")
        self._loading_combo = False

    def load_cached_shelves(self):
        token = self.token_edit.text().strip()
        if not token:
            return False
        cache = prefs.get("hardcover_shelves_cache", {})
        data = cache.get(self._hardcover_cache_key(token)) if isinstance(cache, dict) else None
        if not data:
            return False
        self._populate_shelves(data.get("data", data))
        self.fetch_shelves_btn.setText("Refresh Shelves")
        self.on_load_books(force_refresh=False)
        return True

    def save_cached_shelves(self, token, data):
        cache = prefs.get("hardcover_shelves_cache", {})
        if not isinstance(cache, dict):
            cache = {}
        cache[self._hardcover_cache_key(token)] = {"saved_at": int(time.time()), "data": data}
        prefs["hardcover_shelves_cache"] = cache

    def load_cached_books(self, token, shelf_type, target_id):
        cache = prefs.get("hardcover_books_cache", {})
        key = self._books_cache_key(token, shelf_type, target_id)
        entry = cache.get(key) if isinstance(cache, dict) else None
        if not entry:
            return False
        self.fetched_books = entry.get("books", entry) if isinstance(entry, dict) else entry
        self.populate_books_table()
        return True

    def save_cached_books(self, token, shelf_type, target_id, books):
        cache = prefs.get("hardcover_books_cache", {})
        if not isinstance(cache, dict):
            cache = {}
        cache[self._books_cache_key(token, shelf_type, target_id)] = {
            "saved_at": int(time.time()),
            "books": books,
        }
        prefs["hardcover_books_cache"] = cache

    def on_fetch_shelves(self, force_refresh=False):
        token = self.token_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "Token Required", "Please enter your Hardcover API token.")
            return

        prefs["hardcover_token"] = token
        if not force_refresh and self.load_cached_shelves():
            return

        self.fetch_shelves_btn.setEnabled(False)
        self.fetch_shelves_btn.setText("Fetching...")

        try:
            data = fetch_user_shelves_and_lists(token)
            self.save_cached_shelves(token, data)
            self._populate_shelves(data)

            self.fetch_shelves_btn.setText("Refresh Shelves")
            self.fetch_shelves_btn.setEnabled(True)
            self.on_load_books(force_refresh=True)
        except Exception as e:
            self.fetch_shelves_btn.setText("Refresh Shelves")
            self.fetch_shelves_btn.setEnabled(True)
            QMessageBox.critical(self, "Hardcover Error", f"Failed to fetch shelves:\n{e}")

    def on_shelf_selected(self, idx):
        if idx >= 0 and not self._loading_combo:
            self.on_load_books(force_refresh=False)

    def on_load_books(self, force_refresh=False):
        token = self.token_edit.text().strip()
        if not token or self.shelf_combo.currentIndex() < 0:
            return

        current_item = self.shelf_combo.currentData()
        if not current_item or not isinstance(current_item, dict):
            return

        shelf_type = current_item.get("type", "status")
        target_id = current_item.get("id", 1)

        if not force_refresh and self.load_cached_books(token, shelf_type, target_id):
            return

        self.load_books_btn.setEnabled(False)
        self.load_books_btn.setText("Loading...")

        try:
            books = fetch_shelf_books(token, shelf_type=shelf_type, target_id=target_id)
            self.save_cached_books(token, shelf_type, target_id, books)
            self.fetched_books = books
            self.populate_books_table()
            self.load_books_btn.setText("Refresh Books")
            self.load_books_btn.setEnabled(True)
        except Exception as e:
            self.load_books_btn.setText("Refresh Books")
            self.load_books_btn.setEnabled(True)
            QMessageBox.warning(self, "Load Error", f"Could not load books for shelf:\n{e}")

    def populate_books_table(self):
        self.books_table.setRowCount(len(self.fetched_books))
        for row, b in enumerate(self.fetched_books):
            self.books_table.setItem(row, 0, QTableWidgetItem(b.get("title", "")))
            self.books_table.setItem(row, 1, QTableWidgetItem(b.get("author", "")))
            isbn = b.get("best_isbn") or b.get("isbn_13") or b.get("isbn_10") or ""
            isbn_item = QTableWidgetItem(isbn if isbn else "—")
            if not isbn:
                isbn_item.setForeground(self.palette().color(self.foregroundRole()))
            self.books_table.setItem(row, 2, isbn_item)
            self.books_table.setItem(row, 3, QTableWidgetItem(str(b.get("release_year") or "")))
            self.books_table.setItem(row, 4, QTableWidgetItem("Ready"))
        self.books_table.selectAll()

    def select_all_books(self):
        self.books_table.selectAll()

    def deselect_all_books(self):
        self.books_table.clearSelection()

    def select_first_n_books(self):
        n = self.max_queue_spin.value()
        if n <= 0:
            n = 10
        self.books_table.clearSelection()
        limit = min(n, self.books_table.rowCount())
        for r in range(limit):
            self.books_table.selectRow(r)

    def _is_in_library(self, isbn="", title=""):
        try:
            gui = getattr(self.parent_dialog, "gui", None)
            if not gui or not getattr(gui, "current_db", None):
                return False
            db = gui.current_db
            new_api = getattr(db, "new_api", None)
            if isbn and new_api:
                clean_isbn = isbn.replace("-", "").strip()
                if clean_isbn and new_api.search(f"isbn:{clean_isbn}"):
                    return True
            elif isbn and hasattr(db, "data"):
                clean_isbn = isbn.replace("-", "").strip()
                if clean_isbn and db.data.search(f"isbn:{clean_isbn}"):
                    return True
            if title and new_api:
                clean_t = title.replace('"', '').strip()
                if clean_t and new_api.search(f'title:"={clean_t}"'):
                    return True
        except Exception:
            pass
        return False

    def on_queue_selected(self):
        selected_rows = sorted(set(idx.row() for idx in self.books_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select at least one book from the table.")
            return

        max_limit = self.max_queue_spin.value()
        if max_limit > 0 and len(selected_rows) > max_limit:
            selected_rows = selected_rows[:max_limit]

        is_isbn_mode = self.isbn_mode_radio.isChecked()
        skip_library = self.skip_library_checkbox.isChecked()

        added_books = []
        skipped_no_isbn = 0
        skipped_in_lib = 0

        for r in selected_rows:
            if r >= len(self.fetched_books):
                continue
            b = self.fetched_books[r]
            title = b.get("title", "")
            author = b.get("author", "")
            isbn = b.get("best_isbn") or b.get("isbn_13") or b.get("isbn_10") or ""

            if is_isbn_mode and not isbn:
                skipped_no_isbn += 1
                self.books_table.setItem(r, 4, QTableWidgetItem("Skipped (No ISBN)"))
                continue

            if skip_library and self._is_in_library(isbn, title):
                skipped_in_lib += 1
                self.books_table.setItem(r, 4, QTableWidgetItem("Skipped (In Library)"))
                continue

            rec = {
                "title": title,
                "author": author,
                "isbn": isbn if is_isbn_mode else (isbn or ""),
                "isbn_only": is_isbn_mode,
                "year": b.get("release_year") or "",
            }
            added_books.append(rec)
            self.books_table.setItem(r, 4, QTableWidgetItem("✓ In Search Queue"))

        if not added_books:
            msg = "No books were added to Search Queue."
            if skipped_in_lib:
                msg += f"\n• {skipped_in_lib} book(s) already in Calibre library."
            if skipped_no_isbn:
                msg += f"\n• {skipped_no_isbn} book(s) lacked an ISBN."
            QMessageBox.information(self, "No Books Queued", msg)
            return

        if self.parent_dialog:
            if not hasattr(self.parent_dialog, "selected_books") or self.parent_dialog.selected_books is None:
                self.parent_dialog.selected_books = []

            existing_sigs = {
                (b.get("isbn", "").strip(), b.get("title", "").strip().lower())
                for b in self.parent_dialog.selected_books
            }
            new_count = 0
            for rec in added_books:
                sig = (rec.get("isbn", "").strip(), rec.get("title", "").strip().lower())
                if sig not in existing_sigs:
                    self.parent_dialog.selected_books.append(rec)
                    existing_sigs.add(sig)
                    new_count += 1

            if hasattr(self.parent_dialog, "update_search_queue_bar"):
                self.parent_dialog.update_search_queue_bar()

            self.parent_dialog.status_label.setText(
                f"Loaded {len(self.parent_dialog.selected_books)} record(s) into Search Queue ({new_count} new from Hardcover)."
            )

        summary_msg = f"✓ Added {len(added_books)} book(s) to the Search Queue."
        if skipped_in_lib:
            summary_msg += f"\n• Skipped {skipped_in_lib} book(s) already in Calibre library."
        if skipped_no_isbn:
            summary_msg += f"\n• Skipped {skipped_no_isbn} book(s) with no ISBN."

        QMessageBox.information(self, "Hardcover Search Queue", summary_msg)
        self.accept()

    def restore_state(self):
        state_hex = prefs.get("hardcover_books_table_header", "")
        if state_hex:
            try:
                self.books_table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode("ascii")))
            except Exception:
                pass

    def save_state(self):
        prefs["hardcover_dialog_width"] = self.width()
        prefs["hardcover_dialog_height"] = self.height()
        try:
            prefs["hardcover_books_table_header"] = bytes(
                self.books_table.horizontalHeader().saveState().toHex()
            ).decode("ascii")
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_state()
        super().closeEvent(event)

    def accept(self):
        self.save_state()
        super().accept()

    def reject(self):
        self.save_state()
        super().reject()


class ReviewImportDialog(QDialog):
    """Review modal presented after download completion or abortion to select books for Calibre import."""

    def __init__(self, downloaded_items, is_aborted=False, stats_summary=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Downloaded Books for Import")
        saved_w = min(1200, max(560, int(prefs.get("review_dialog_width", 760))))
        saved_h = min(900, max(360, int(prefs.get("review_dialog_height", 420))))
        self.resize(saved_w, saved_h)
        self.downloaded_items = downloaded_items
        self.is_aborted = is_aborted
        self.stats_summary = stats_summary or {}
        self.approved_items = []

        layout = QVBoxLayout(self)

        status_prefix = "<b>Download stopped early.</b> " if is_aborted else "<b>Bulk download finished.</b> "
        info_text = (
            f"{status_prefix}{len(downloaded_items)} book(s) were successfully downloaded.<br>"
            "Review and choose which books to import into your Calibre library:"
        )
        if self.stats_summary:
            s = self.stats_summary
            cdn_str = ""
            if s.get("fastest_cdns"):
                top_cdn, top_speed = s["fastest_cdns"][0]
                cdn_str = f" &nbsp;|&nbsp; 🚀 CDN: <b>{top_cdn}</b> ({top_speed:.1f} KB/s)"
            info_text += (
                f"<br><span style='font-size: 12px; font-weight: normal;'>"
                f"⏱ Time: <b>{s.get('time_str', '-')}</b> &nbsp;|&nbsp; "
                f"📦 Data: <b>{s.get('size_str', '-')}</b> &nbsp;|&nbsp; "
                f"⚡ Avg Speed: <b>{s.get('speed_str', '-')}</b>{cdn_str}</span>"
            )
        banner = QLabel(info_text, self)
        banner.setWordWrap(True)
        banner.setStyleSheet("padding: 10px 14px; background: palette(alternate-base); color: palette(text); border-radius: 4px; font-size: 13px;")
        layout.addWidget(banner)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Import?", "Title", "Author", "Format", "Size"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table.setRowCount(len(downloaded_items))
        for row, item in enumerate(downloaded_items):
            book = item["book"]
            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, cb_item)
            self.table.setItem(row, 1, QTableWidgetItem(book.title or "Unknown"))
            self.table.setItem(row, 2, QTableWidgetItem(book.author or "Unknown"))
            self.table.setItem(row, 3, QTableWidgetItem(book.extension or "EPUB"))
            self.table.setItem(row, 4, QTableWidgetItem(book.size or "-"))

        state_hex = prefs.get("review_table_header", "")
        if state_hex:
            try:
                self.table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode("ascii")))
            except Exception:
                pass

        layout.addWidget(self.table)

        sel_bar = QHBoxLayout()
        sel_all_btn = QPushButton("Select All", self)
        sel_all_btn.clicked.connect(self.select_all)
        sel_bar.addWidget(sel_all_btn)

        desel_all_btn = QPushButton("Deselect All", self)
        desel_all_btn.clicked.connect(self.deselect_all)
        sel_bar.addWidget(desel_all_btn)

        sel_bar.addStretch()
        layout.addLayout(sel_bar)

        btn_bar = QHBoxLayout()
        discard_btn = QPushButton("Discard / Skip", self)
        discard_btn.clicked.connect(self.reject)
        btn_bar.addWidget(discard_btn)

        btn_bar.addStretch()

        import_sel_btn = QPushButton("Import Selected", self)
        import_sel_btn.clicked.connect(self.accept_selected)
        btn_bar.addWidget(import_sel_btn)

        import_all_btn = QPushButton("Import All", self)
        import_all_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        import_all_btn.clicked.connect(self.accept_all)
        btn_bar.addWidget(import_all_btn)

        layout.addLayout(btn_bar)

    def select_all(self):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Checked)

    def deselect_all(self):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Unchecked)

    def accept_all(self):
        self.approved_items = list(self.downloaded_items)
        self.accept()

    def accept_selected(self):
        self.approved_items = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.CheckState.Checked:
                self.approved_items.append(self.downloaded_items[r])
        self.accept()

    def save_state(self):
        prefs["review_dialog_width"] = self.width()
        prefs["review_dialog_height"] = self.height()
        try:
            prefs["review_table_header"] = bytes(
                self.table.horizontalHeader().saveState().toHex()
            ).decode("ascii")
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_state()
        super().closeEvent(event)

    def accept(self):
        self.save_state()
        super().accept()

    def reject(self):
        self.save_state()
        super().reject()


class LibgenDialog(QDialog):
    def __init__(self, gui, initial_query=None, selected_books=None, parent=None):
        super().__init__(parent or gui)
        self.gui = gui
        self.initial_query = initial_query
        self.selected_books = list(selected_books) if selected_books else []
        self.setWindowTitle(f"LibGen Downloader ({PLUGIN_VERSION_STR})")
        saved_w = min(1150, max(850, int(prefs.get("dialog_width", 980))))
        saved_h = min(800, max(550, int(prefs.get("dialog_height", 620))))
        self.resize(saved_w, saved_h)

        self.search_results = []
        self.queue_items = []
        self.mirror_health = {}
        self.download_worker = None
        self.search_worker = None
        self.search_queue_worker = None
        self.health_worker = None
        
        # Debounce timer for saving preferences
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self._do_save_all_field_preferences)

        # In-memory cover cache and text loading animation timer
        self.cover_cache = OrderedDict()
        self.cover_anim_timer = QTimer(self)
        self.cover_anim_timer.setInterval(110)
        self.cover_anim_timer.timeout.connect(self.update_cover_animation)
        self.cover_anim_frame = 0

        # Debounce timer for queue filtering
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self.apply_queue_filter)

        # Download stats and cats toggle (toggled by triple-clicking version badge)
        self.show_stats = bool(prefs.get("show_download_stats", False))
        self.show_cats = bool(prefs.get("show_cats", False))
        self.version_click_count = 0
        self.version_click_timer = QTimer(self)
        self.version_click_timer.setInterval(1200)
        self.version_click_timer.setSingleShot(True)
        self.version_click_timer.timeout.connect(self._reset_version_clicks)

        cleanup_expired_history()
        self._setup_ui()
        self.populate_mirrors_table()
        self.load_queue()

    def _setup_ui(self):
        base_layout = QHBoxLayout(self)
        
        left_widget = QWidget()
        main_layout = QVBoxLayout(left_widget)
        base_layout.addWidget(left_widget, stretch=5)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_layout.addWidget(QLabel("<b>Cover Preview</b>"))
        self.cover_label = QLabel("No Selection", self)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_w = min(360, max(140, int(prefs.get("cover_panel_width", 200))))
        cover_h = min(520, max(180, int(prefs.get("cover_panel_height", 300))))
        self.cover_label.setFixedSize(cover_w, cover_h)
        self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")
        self.cover_label.setScaledContents(False)
        right_layout.addWidget(self.cover_label)

        self.side_neko_label = QLabel("(=^.^=) watching mirrors", self)
        self.side_neko_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.side_neko_label.setStyleSheet(
            "font-family: monospace; font-weight: 600; font-size: 12px; "
            "color: palette(text); padding: 4px; background: palette(base); "
            "border: 1px solid palette(mid); border-radius: 4px;"
        )
        self.side_neko_label.setVisible(self.show_cats)
        right_layout.addWidget(self.side_neko_label)

        right_layout.addWidget(QLabel("<b>Live Mirror Status</b>"))
        self.side_mirror_status = QPlainTextEdit(self)
        self.side_mirror_status.setReadOnly(True)
        self.side_mirror_status.setFixedWidth(200)
        self.side_mirror_status.setStyleSheet(MONO_PANEL_STYLE)
        right_layout.addWidget(self.side_mirror_status)
        base_layout.addWidget(right_widget, stretch=1)

        # Top Panel: Clean Primary Search Bar + Collapsible Advanced Drawer
        top_panel = QVBoxLayout()
        top_panel.setSpacing(6)

        # --- Row 1 (Primary Search Controls) ---
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        row1.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search title, author, series, ISBN...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.start_search)
        if self.initial_query:
            self.search_input.setText(self.initial_query)
            self.search_input.selectAll()
        row1.addWidget(self.search_input, stretch=4)

        row1.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(SUPPORTED_FORMATS)
        cur_fmt = prefs.get("preferred_format", "Any").upper()
        fmt_idx = self.format_combo.findText(cur_fmt)
        if fmt_idx >= 0:
            self.format_combo.setCurrentIndex(fmt_idx)
        self.format_combo.currentTextChanged.connect(self.save_all_field_preferences)
        row1.addWidget(self.format_combo)

        row1.addWidget(QLabel("Lang:"))
        self.lang_combo = CheckableComboBox(self)
        self.lang_combo.setMinimumWidth(85)
        saved_langs = prefs.get("preferred_languages")
        if not saved_langs:
            single = prefs.get("preferred_language", "English")
            saved_langs = [single] if single else ["English"]
        self.lang_combo.add_checkable_items(SUPPORTED_LANGUAGES, saved_langs)
        self.lang_combo.selection_changed.connect(self.save_all_field_preferences)
        row1.addWidget(self.lang_combo)

        self.search_btn = QPushButton("Search", self)
        self.search_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.search_btn.clicked.connect(self.start_search)
        row1.addWidget(self.search_btn)

        self.stop_search_btn = QPushButton("Stop Search", self)
        self.stop_search_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.stop_search_btn.setVisible(False)
        self.stop_search_btn.clicked.connect(self.stop_search)
        row1.addWidget(self.stop_search_btn)

        self.hardcover_btn = QPushButton("📚 Hardcover", self)
        self.hardcover_btn.setToolTip("Import and queue books from your Hardcover.app shelves / lists")
        self.hardcover_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.hardcover_btn.clicked.connect(self.open_hardcover_dialog)
        row1.addWidget(self.hardcover_btn)

        self.toggle_filters_btn = QPushButton("⚙ Filters ▾", self)
        self.toggle_filters_btn.setToolTip("Toggle secondary search parameters (Field, Category, Mirror, History, Retries)")
        self.toggle_filters_btn.setStyleSheet("padding: 5px 10px;")
        self.toggle_filters_btn.clicked.connect(self.toggle_advanced_filters)
        row1.addWidget(self.toggle_filters_btn)

        top_panel.addLayout(row1)

        # --- Collapsible Advanced Drawer (Row 2) ---
        self.advanced_filters_widget = QWidget(self)
        self.advanced_filters_widget.setObjectName("advanced_filters_widget")
        self.advanced_filters_widget.setStyleSheet(
            "#advanced_filters_widget { background: palette(base); border: 1px solid palette(mid); border-radius: 6px; padding: 4px; }"
        )
        adv_vlayout = QVBoxLayout(self.advanced_filters_widget)
        adv_vlayout.setContentsMargins(8, 6, 8, 6)
        adv_vlayout.setSpacing(6)

        adv_row1 = QHBoxLayout()
        adv_row1.setSpacing(8)

        adv_row1.addWidget(QLabel("Field:"))
        self.field_combo = QComboBox(self)
        self.field_combo.setMaximumWidth(120)
        self.field_combo.addItems(list(SEARCH_FIELDS.keys()))
        cur_field = prefs.get("search_field", "All Fields")
        f_idx = self.field_combo.findText(cur_field)
        if f_idx >= 0:
            self.field_combo.setCurrentIndex(f_idx)
        self.field_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.field_combo)

        adv_row1.addWidget(QLabel("Cat:"))
        self.category_combo = QComboBox(self)
        self.category_combo.setMaximumWidth(140)
        self.category_combo.addItems(list(CATEGORIES.keys()))
        cur_cat = prefs.get("search_category", "All Categories")
        c_idx = self.category_combo.findText(cur_cat)
        if c_idx >= 0:
            self.category_combo.setCurrentIndex(c_idx)
        self.category_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.category_combo)

        adv_row1.addWidget(QLabel("Max:"))
        self.max_results_spinbox = QSpinBox(self)
        self.max_results_spinbox.setMaximumWidth(65)
        self.max_results_spinbox.setRange(1, 1000)
        self.max_results_spinbox.setValue(int(prefs.get("max_results", 5)))
        self.max_results_spinbox.valueChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.max_results_spinbox)

        adv_row1.addWidget(QLabel("Mirror:"))
        self.mirror_combo = QComboBox(self)
        self.mirror_combo.setMaximumWidth(150)
        self.update_mirror_combobox()
        self.mirror_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.mirror_combo)

        self.fetch_mirrors_btn = QPushButton("Fetch Live")
        self.fetch_mirrors_btn.setToolTip("Fetch active mirrors from open-slum.org")
        self.fetch_mirrors_btn.clicked.connect(self.manual_fetch_mirrors)
        adv_row1.addWidget(self.fetch_mirrors_btn)
        adv_row1.addStretch(1)
        adv_vlayout.addLayout(adv_row1)

        adv_row2 = QHBoxLayout()
        adv_row2.setSpacing(8)

        adv_row2.addWidget(QLabel("Mode:"))
        self.filter_combo = QComboBox(self)
        self.filter_combo.setMaximumWidth(110)
        self.filter_combo.addItems(FILTER_MODES)
        cur_mode = prefs.get("filter_mode", "Prioritize")
        m_idx = self.filter_combo.findText(cur_mode)
        if m_idx >= 0:
            self.filter_combo.setCurrentIndex(m_idx)
        self.filter_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row2.addWidget(self.filter_combo)

        self.unique_checkbox = QCheckBox("Unique", self)
        self.unique_checkbox.setToolTip("Filter out duplicate books (same title, author, and format)")
        self.unique_checkbox.setChecked(bool(prefs.get("unique_results", True)))
        self.unique_checkbox.stateChanged.connect(self.save_all_field_preferences)
        adv_row2.addWidget(self.unique_checkbox)

        self.history_checkbox = QCheckBox("History", self)
        self.history_checkbox.setToolTip(
            f"Opt-in: Save search queries to local file and enable autocomplete ({get_search_history_filepath()})"
        )
        self.history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
        self.history_checkbox.stateChanged.connect(self.on_history_toggled)
        adv_row2.addWidget(self.history_checkbox)

        self.history_settings_btn = QPushButton("⚙", self)
        self.history_settings_btn.setToolTip("Configure search & download history limits and auto-retention")
        self.history_settings_btn.setFixedWidth(26)
        self.history_settings_btn.clicked.connect(self.open_history_settings)
        adv_row2.addWidget(self.history_settings_btn)

        # Pending Searches Sub-widget (only visible if pending items exist)
        self.pending_widget = QWidget(self)
        pending_layout = QHBoxLayout(self.pending_widget)
        pending_layout.setContentsMargins(0, 0, 0, 0)
        pending_layout.setSpacing(4)
        pending_layout.addWidget(QLabel("Pending:"))
        self.pending_combo = QComboBox(self)
        self.pending_combo.setMaximumWidth(180)
        self.pending_combo.setToolTip("Select a failed or zero-result search to retry")
        self.pending_combo.currentIndexChanged.connect(self.on_pending_selected)
        pending_layout.addWidget(self.pending_combo)

        self.pending_clear_btn = QPushButton("✕", self)
        self.pending_clear_btn.setToolTip("Remove selected pending search query")
        self.pending_clear_btn.setFixedWidth(24)
        self.pending_clear_btn.clicked.connect(self.remove_selected_pending)
        pending_layout.addWidget(self.pending_clear_btn)
        adv_row2.addWidget(self.pending_widget)

        adv_row2.addStretch(1)
        adv_vlayout.addLayout(adv_row2)

        # Restore expanded/collapsed state from preferences
        show_adv = bool(prefs.get("show_advanced_filters", False))
        self.advanced_filters_widget.setVisible(show_adv)
        self.toggle_filters_btn.setText("⚙ Filters ▴" if show_adv else "⚙ Filters ▾")
        top_panel.addWidget(self.advanced_filters_widget)

        # Batch Calibre Records Search Queue Bar (if books selected from Calibre)
        self.search_queue_bar = QWidget(self)
        queue_bar_layout = QHBoxLayout(self.search_queue_bar)
        queue_bar_layout.setContentsMargins(8, 6, 8, 6)
        self.search_queue_bar.setStyleSheet(
            PANEL_STYLE
        )

        n_books = len(self.selected_books)
        self.queue_info_label = QLabel(f"📚 <b>{n_books} Calibre record(s)</b> loaded into Search Queue", self)
        queue_bar_layout.addWidget(self.queue_info_label)

        self.start_queue_search_btn = QPushButton(f"▶ Search All ({n_books}) Records (Max 2/book)", self)
        self.start_queue_search_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.start_queue_search_btn.clicked.connect(self.start_search_queue)
        queue_bar_layout.addWidget(self.start_queue_search_btn)

        self.stop_queue_search_btn = QPushButton("Stop Queue Search", self)
        self.stop_queue_search_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.stop_queue_search_btn.setVisible(False)
        self.stop_queue_search_btn.clicked.connect(self.stop_search_queue)
        queue_bar_layout.addWidget(self.stop_queue_search_btn)

        self.dismiss_queue_bar_btn = QPushButton("✕", self)
        self.dismiss_queue_bar_btn.setToolTip("Dismiss Calibre records search queue")
        self.dismiss_queue_bar_btn.setFixedWidth(24)
        self.dismiss_queue_bar_btn.clicked.connect(self.dismiss_search_queue_bar)
        queue_bar_layout.addWidget(self.dismiss_queue_bar_btn)

        if not self.selected_books:
            self.search_queue_bar.setVisible(False)

        top_panel.addWidget(self.search_queue_bar)
        main_layout.addLayout(top_panel)
        self.setup_search_completer()

        # Tabs: Search Results, Queue, and Mirrors/Health
        self.tabs = QTabWidget(self)
        self.tabs.setMovable(True)
        self.tabs.currentChanged.connect(self.on_table_selection_changed)

        # --- Tab 1: Search Results ---
        self.tab_results = QWidget()
        self.tab_results.setObjectName("tab_results")
        results_layout = QVBoxLayout(self.tab_results)

        # Inline Search Progress & Active Mirror Display
        search_status_box = QHBoxLayout()
        self.search_mirror_label = QLabel("Search status: Ready", self)
        self.search_mirror_label.setStyleSheet("font-weight: 600; color: palette(highlight);")
        search_status_box.addWidget(self.search_mirror_label, stretch=2)

        self.search_progress_bar = QProgressBar(self)
        self.search_progress_bar.setFixedHeight(16)
        self.search_progress_bar.setMaximumWidth(300)
        self.search_progress_bar.setTextVisible(True)
        self.search_progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.search_progress_bar.setVisible(False)
        search_status_box.addWidget(self.search_progress_bar, stretch=1)

        results_layout.addLayout(search_status_box)

        self.results_table = QTableWidget(self)
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "Title", "Author", "Publisher / Year", "Language", "Format", "Size"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.results_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSortingEnabled(True)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_results_context_menu)
        results_layout.addWidget(self.results_table)

        # Global shortcut: Ctrl+Shift+A to add selected to queue
        self.queue_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self.queue_shortcut.activated.connect(self.queue_selected_results)

        # Results Bottom Buttons
        btn_bar = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All", self)
        self.select_all_btn.clicked.connect(self.select_all_results)
        btn_bar.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All", self)
        self.deselect_all_btn.clicked.connect(self.deselect_all_results)
        btn_bar.addWidget(self.deselect_all_btn)

        self.discard_selected_results_btn = QPushButton("Discard Selected", self)
        self.discard_selected_results_btn.clicked.connect(self.discard_selected_results)
        btn_bar.addWidget(self.discard_selected_results_btn)

        btn_bar.addStretch()

        self.queue_selected_btn = QPushButton("Add to Queue", self)
        self.queue_selected_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.queue_selected_btn.clicked.connect(self.queue_selected_results)
        btn_bar.addWidget(self.queue_selected_btn)

        self.download_now_btn = QPushButton("Download Selected", self)
        self.download_now_btn.clicked.connect(self.download_selected_now)
        btn_bar.addWidget(self.download_now_btn)

        results_layout.addLayout(btn_bar)
        self.tabs.addTab(self.tab_results, "Search Results (0)")

        # --- Tab 2: Download Queue ---
        self.tab_queue = QWidget()
        self.tab_queue.setObjectName("tab_queue")
        queue_layout = QVBoxLayout(self.tab_queue)

        # Queue Segmentation: Queued, Downloading, Downloaded, Failed
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("View:"))
        self.queue_filter_mode = "Queued"
        self.queue_filter_btns = {}

        for mode in ("Queued", "Downloading", "Downloaded", "Failed"):
            btn = QPushButton(f"{mode} (0)", self)
            btn.setCheckable(True)
            if mode == "Queued":
                btn.setChecked(True)
                btn.setStyleSheet(FILTER_BUTTON_ACTIVE_STYLE)
            else:
                btn.setStyleSheet(FILTER_BUTTON_STYLE)
            btn.clicked.connect(lambda checked, m=mode: self.set_queue_filter(m))
            filter_bar.addWidget(btn)
            self.queue_filter_btns[mode] = btn

        filter_bar.addStretch(1)
        queue_layout.addLayout(filter_bar)

        # Dedicated Session / Overall Bulk Download Progress Bar
        self.bulk_progress_bar = QProgressBar(self)
        self.bulk_progress_bar.setFixedHeight(18)
        self.bulk_progress_bar.setTextVisible(True)
        self.bulk_progress_bar.setFormat("Bulk Download: Ready (0/0)")
        self.bulk_progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.bulk_progress_bar.setVisible(False)
        queue_layout.addWidget(self.bulk_progress_bar)

        self.queue_table = QTableWidget(self)
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels([
            "Title", "Author", "Format", "Size", "Status", "Speed", "Progress"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.queue_table.setItemDelegateForColumn(6, ProgressBarDelegate(self.queue_table))
        queue_layout.addWidget(self.queue_table)

        # Collapsible Live Activity Log
        log_header_box = QHBoxLayout()
        self.log_toggle_btn = QPushButton("▶ Live Activity Log", self)
        self.log_toggle_btn.setFlat(True)
        self.log_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_toggle_btn.setStyleSheet("text-align: left; font-weight: 600; color: palette(text); font-size: 11px; padding: 2px;")
        self.log_toggle_btn.clicked.connect(self.toggle_activity_log)
        log_header_box.addWidget(self.log_toggle_btn)
        log_header_box.addStretch(1)
        queue_layout.addLayout(log_header_box)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        log_h = min(320, max(70, int(prefs.get("log_panel_height", 120))))
        self.log_view.setFixedHeight(log_h)
        self.log_view.setStyleSheet(MONO_PANEL_STYLE)
        self.log_view.setPlaceholderText("Live download events, mirror cycles, and streaming chunks will appear here...")
        self.log_view.setVisible(False)
        queue_layout.addWidget(self.log_view)

        # Queue Bottom Buttons (Two compact rows)
        q_row1 = QHBoxLayout()
        self.clear_downloaded_btn = QPushButton("Clear Finished", self)
        self.clear_downloaded_btn.setToolTip("Remove downloaded / completed items from queue")
        self.clear_downloaded_btn.clicked.connect(self.clear_downloaded_items)
        q_row1.addWidget(self.clear_downloaded_btn)

        self.remove_queue_btn = QPushButton("Remove Selected", self)
        self.remove_queue_btn.clicked.connect(self.remove_from_queue)
        q_row1.addWidget(self.remove_queue_btn)

        self.clear_queue_btn = QPushButton("Clear Queue", self)
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        q_row1.addWidget(self.clear_queue_btn)

        self.retry_failed_btn = QPushButton("Retry Failed", self)
        self.retry_failed_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.retry_failed_btn.clicked.connect(self.retry_failed_downloads)
        q_row1.addWidget(self.retry_failed_btn)
        q_row1.addStretch(1)
        queue_layout.addLayout(q_row1)

        q_row2 = QHBoxLayout()
        self.fast_mode_checkbox = QCheckBox("⚡ Fast Mode", self)
        self.fast_mode_checkbox.setToolTip("Fast Mode: 3s mirror probe, skips dead/troubled downloads immediately to Failed list")
        self.fast_mode_checkbox.setChecked(bool(prefs.get("fast_mode", False)))
        self.fast_mode_checkbox.stateChanged.connect(self.save_all_field_preferences)
        q_row2.addWidget(self.fast_mode_checkbox)

        self.auto_retry_checkbox = QCheckBox("Auto-retry until all downloaded", self)
        self.auto_retry_checkbox.setChecked(False)
        q_row2.addWidget(self.auto_retry_checkbox)

        q_row2.addWidget(QLabel("After:"))
        self.download_action_combo = QComboBox(self)
        self.download_action_combo.addItems(["Import to Calibre", "Save to Folder"])
        action_idx = self.download_action_combo.findText(prefs.get("download_action", "Import to Calibre"))
        if action_idx >= 0:
            self.download_action_combo.setCurrentIndex(action_idx)
        self.download_action_combo.currentTextChanged.connect(self.save_all_field_preferences)
        q_row2.addWidget(self.download_action_combo)

        self.download_dir_btn = QPushButton("Folder...", self)
        self.download_dir_btn.setToolTip("Choose where downloaded files are saved")
        self.download_dir_btn.clicked.connect(self.choose_download_directory)
        q_row2.addWidget(self.download_dir_btn)

        q_row2.addStretch(1)

        self.stop_download_btn = QPushButton("Stop Download", self)
        self.stop_download_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.clicked.connect(self.stop_bulk_download)
        q_row2.addWidget(self.stop_download_btn)

        self.start_download_btn = QPushButton("Start Bulk Download", self)
        self.start_download_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.start_download_btn.clicked.connect(lambda: self.start_bulk_download())
        q_row2.addWidget(self.start_download_btn)

        queue_layout.addLayout(q_row2)
        self.tabs.addTab(self.tab_queue, "Queue (0)")


        # --- Tab 3: Mirrors & Health ---
        self.tab_mirrors = QWidget()
        self.tab_mirrors.setObjectName("tab_mirrors")
        mirrors_layout = QVBoxLayout(self.tab_mirrors)

        # Mirrors Table
        self.mirrors_table = QTableWidget(self)
        self.mirrors_table.setColumnCount(6)
        self.mirrors_table.setHorizontalHeaderLabels([
            "Mirror URL", "Status", "Latency", "Speed", "Type", "Action"
        ])
        self.mirrors_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        mirrors_layout.addWidget(self.mirrors_table)

        # Mirror Controls
        mirror_actions_bar = QHBoxLayout()
        self.test_all_mirrors_btn = QPushButton("Ping / Test All Mirrors", self)
        self.test_all_mirrors_btn.clicked.connect(self.test_all_mirrors)
        mirror_actions_bar.addWidget(self.test_all_mirrors_btn)

        self.sort_speed_btn = QPushButton("Sort by Speed", self)
        self.sort_speed_btn.setStyleSheet("font-weight: bold;")
        self.sort_speed_btn.clicked.connect(self.sort_mirrors_by_speed)
        mirror_actions_bar.addWidget(self.sort_speed_btn)

        self.set_primary_btn = QPushButton("Set Selected as Primary", self)
        self.set_primary_btn.clicked.connect(self.set_selected_mirror_primary)
        mirror_actions_bar.addWidget(self.set_primary_btn)

        self.discard_dead_btn = QPushButton("Discard Dead Mirrors", self)
        self.discard_dead_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.discard_dead_btn.setToolTip("Remove mirrors that failed latency/bandwidth tests from your configured mirrors")
        self.discard_dead_btn.clicked.connect(self.discard_dead_mirrors)
        mirror_actions_bar.addWidget(self.discard_dead_btn)

        mirror_actions_bar.addStretch()
        mirrors_layout.addLayout(mirror_actions_bar)

        # Add Custom Mirror Box
        add_group = QGroupBox("Add Custom Mirror")
        add_layout = QHBoxLayout(add_group)
        self.add_mirror_input = QLineEdit(self)
        self.add_mirror_input.setPlaceholderText("https://libgen.is or custom mirror URL...")
        self.add_mirror_input.returnPressed.connect(self.add_custom_mirror_handler)
        add_layout.addWidget(self.add_mirror_input, stretch=3)

        self.add_mirror_btn = QPushButton("Add Mirror", self)
        self.add_mirror_btn.clicked.connect(self.add_custom_mirror_handler)
        add_layout.addWidget(self.add_mirror_btn)

        mirrors_layout.addWidget(add_group)
        self.tabs.addTab(self.tab_mirrors, "Mirrors & Health")

        main_layout.addWidget(self.tabs)

        # Bottom Progress & Status Bar
        status_bar = QHBoxLayout()
        self.status_label = QLabel("Ready", self)
        status_bar.addWidget(self.status_label, stretch=2)



        # ASCII Cat (Neko) Animation Label
        self.neko_label = QLabel("(=^.^=)zZ", self)
        self.neko_label.setFixedWidth(85)
        self.neko_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.neko_label.setStyleSheet("font-family: monospace; font-weight: 600; font-size: 13px; color: palette(text);")
        self.neko_label.setVisible(self.show_cats)
        status_bar.addWidget(self.neko_label)

        self.neko_timer = QTimer(self)
        self.neko_timer.timeout.connect(self.update_neko_animation)
        self.neko_frame_idx = 0
        self.neko_timer.start(400)

        # Version Badge in Status Bar (Click 3x to toggle hidden download stats)
        self.version_badge = QLabel(PLUGIN_VERSION_STR, self)
        self.version_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_badge.mousePressEvent = self.on_version_badge_clicked
        self._update_version_badge_style()
        status_bar.addWidget(self.version_badge)

        main_layout.addLayout(status_bar)

        self.restore_header_states()
        self.update_pending_combo()

    def update_pending_combo(self):
        if not hasattr(self, "pending_combo"):
            return
        pending = get_pending_searches()
        self.pending_combo.blockSignals(True)
        self.pending_combo.clear()
        if not pending:
            self.pending_combo.addItem("None (0)")
            self.pending_combo.setEnabled(False)
            if hasattr(self, "pending_clear_btn"):
                self.pending_clear_btn.setEnabled(False)
            if hasattr(self, "pending_widget"):
                self.pending_widget.setVisible(False)
        else:
            self.pending_combo.addItem(f"Pending ({len(pending)})...", None)
            for p in pending:
                display_p = p if len(p) <= 24 else (p[:21] + "...")
                self.pending_combo.addItem(display_p, p)
            self.pending_combo.setEnabled(True)
            if hasattr(self, "pending_clear_btn"):
                self.pending_clear_btn.setEnabled(True)
            if hasattr(self, "pending_widget"):
                self.pending_widget.setVisible(True)
        self.pending_combo.blockSignals(False)

    def on_pending_selected(self, idx):
        if idx <= 0:
            return
        query = self.pending_combo.currentData()
        if query:
            self.search_input.setText(query)
            self.search_input.selectAll()

    def remove_selected_pending(self):
        idx = self.pending_combo.currentIndex()
        if idx > 0:
            query = self.pending_combo.currentData()
            if query:
                remove_pending_search(query)
                self.update_pending_combo()

    def open_hardcover_dialog(self):
        dlg = HardcoverShelfDialog(self)
        dlg.exec()

    def set_tab_text_for_widget(self, widget, text):
        if hasattr(self, "tabs") and widget is not None:
            idx = self.tabs.indexOf(widget)
            if idx >= 0:
                self.tabs.setTabText(idx, text)

    def set_current_tab_widget(self, widget):
        if hasattr(self, "tabs") and widget is not None:
            idx = self.tabs.indexOf(widget)
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)

    def save_header_states(self):
        try:
            if hasattr(self, "results_table"):
                prefs["results_table_header"] = bytes(self.results_table.horizontalHeader().saveState().toHex()).decode("ascii")
            if hasattr(self, "queue_table"):
                prefs["queue_table_header"] = bytes(self.queue_table.horizontalHeader().saveState().toHex()).decode("ascii")
            if hasattr(self, "mirrors_table"):
                prefs["mirrors_table_header"] = bytes(self.mirrors_table.horizontalHeader().saveState().toHex()).decode("ascii")
            if hasattr(self, "tabs"):
                order = []
                for i in range(self.tabs.count()):
                    w = self.tabs.widget(i)
                    name = w.objectName() if w else ""
                    if name:
                        order.append(name)
                if order:
                    prefs["tabs_order"] = order
            if hasattr(self, "cover_label"):
                prefs["cover_panel_width"] = self.cover_label.width()
                prefs["cover_panel_height"] = self.cover_label.height()
            if hasattr(self, "log_view"):
                prefs["log_panel_height"] = self.log_view.height()
        except Exception as e:
            print(f"[LibGen Plugin] Failed to save header states: {e}")

    def restore_header_states(self):
        try:
            for key, table in [
                ("results_table_header", getattr(self, "results_table", None)),
                ("queue_table_header", getattr(self, "queue_table", None)),
                ("mirrors_table_header", getattr(self, "mirrors_table", None)),
            ]:
                if table and prefs.get(key):
                    state_hex = prefs.get(key)
                    table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode("ascii")))

            if hasattr(self, "tabs") and prefs.get("tabs_order"):
                saved_order = prefs.get("tabs_order")
                named_widgets = {
                    "tab_results": getattr(self, "tab_results", None),
                    "tab_queue": getattr(self, "tab_queue", None),
                    "tab_mirrors": getattr(self, "tab_mirrors", None),
                }
                for target_pos, name in enumerate(saved_order):
                    widget = named_widgets.get(name)
                    if widget:
                        current_pos = self.tabs.indexOf(widget)
                        if current_pos >= 0 and current_pos != target_pos:
                            tab_bar = self.tabs.tabBar()
                            if tab_bar:
                                tab_bar.moveTab(current_pos, target_pos)
        except Exception as e:
            print(f"[LibGen Plugin] Failed to restore header states: {e}")

    def _reset_version_clicks(self):
        self.version_click_count = 0

    def on_version_badge_clicked(self, event):
        self.version_click_count += 1
        self.version_click_timer.start()
        if self.version_click_count >= 3:
            self.version_click_count = 0
            self.version_click_timer.stop()
            self.show_stats = not self.show_stats
            self.show_cats = self.show_stats
            prefs["show_download_stats"] = self.show_stats
            prefs["show_cats"] = self.show_cats
            self._update_version_badge_style()
            if hasattr(self, "neko_label"):
                self.neko_label.setVisible(self.show_cats)
            if hasattr(self, "side_neko_label"):
                self.side_neko_label.setVisible(self.show_cats)
            status_msg = "enabled" if self.show_stats else "disabled"
            self.status_label.setText(f"Cats and stats {status_msg}.")
            self.append_log(f"[CONFIG] Cats and download stats {status_msg} (toggled via version badge).")

    def _update_version_badge_style(self):
        if not hasattr(self, "version_badge"):
            return
        if self.show_stats:
            self.version_badge.setStyleSheet(
                "color: palette(highlight); font-size: 11px; padding: 2px 6px; background: palette(base); border: 1px solid palette(highlight); border-radius: 3px; font-weight: 600;"
            )
            self.version_badge.setToolTip("Cats & download statistics active (Click 3x to hide)")
        else:
            self.version_badge.setStyleSheet(
                "color: palette(text); font-size: 11px; padding: 2px 6px; background: palette(base); border: 1px solid palette(mid); border-radius: 3px;"
            )
            self.version_badge.setToolTip("Version info (Click 3x to toggle cats & stats)")

    def manual_fetch_mirrors(self):
        self.fetch_mirrors_btn.setEnabled(False)
        self.fetch_mirrors_btn.setText("Fetching...")
        
        self.live_mirror_worker = LiveMirrorWorker(parent=self)
        self.live_mirror_worker.mirrors_discovered.connect(self.on_manual_mirrors_discovered)
        self.live_mirror_worker.start()

    def on_manual_mirrors_discovered(self, live_mirrors):
        self.fetch_mirrors_btn.setEnabled(True)
        self.fetch_mirrors_btn.setText("Fetch Live")
        
        if live_mirrors:
            fallback_str = prefs.get("fallback_mirrors", "")
            fallbacks = [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip()]
            added = False
            for m in live_mirrors:
                if m not in fallbacks:
                    fallbacks.append(m)
                    added = True
            
            if added:
                prefs["fallback_mirrors"] = ", ".join(fallbacks)
                self.update_mirror_combobox()
                self.populate_mirrors_table()
                QMessageBox.information(self, "Mirrors Found", f"Successfully fetched and added new active mirrors from open-slum.org!")
            else:
                QMessageBox.information(self, "Mirrors Found", "Fetched live mirrors, but you already have them all in your configuration.")
        else:
            QMessageBox.warning(self, "Fetch Failed", "Could not fetch live mirrors or none were found active.")
    def update_mirror_combobox(self):
        self.mirror_combo.clear()
        self.mirror_combo.addItem("Auto (Best Latency)")
        for m in get_mirrors():
            self.mirror_combo.addItem(m)

        cur_selected = prefs.get("selected_mirror", "Auto")
        if cur_selected == "Auto" or str(cur_selected).startswith("Auto"):
            self.mirror_combo.setCurrentIndex(0)
        else:
            idx = self.mirror_combo.findText(cur_selected)
            if idx >= 0:
                self.mirror_combo.setCurrentIndex(idx)

    def update_neko_animation(self):
        is_active = False
        if hasattr(self, 'search_worker') and self.search_worker and self.search_worker.isRunning():
            is_active = True
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            is_active = True
            
        status_text = self.status_label.text().lower()
        is_error = "error" in status_text or "failed" in status_text or "aborted" in status_text
            
        if is_active:
            frames = ["(=O.O=) _/", "(=O.O=) _|", "(=O.O=) _~", "(=O.O=) _|"]
        elif is_error:
            frames = ["(=>_<=) !!", "(=>_<=)   "]
        else:
            frames = ["(=^.^=) zZ", "(=^.^=)  z", "(=^.^=)   ", "(=^.^=)zZ "]

        if not hasattr(self, 'neko_frame_idx'):
            self.neko_frame_idx = 0
            
        self.neko_frame_idx = (self.neko_frame_idx + 1) % max(len(frames), 10)
        
        if hasattr(self, 'neko_label'):
            self.neko_label.setText(frames[self.neko_frame_idx % len(frames)])
        if hasattr(self, 'side_neko_label'):
            side_frames = [
                "(=^.^=) scanning",
                "(=^.^=) scanning.",
                "(=^.^=) scanning..",
                "(=^.^=) scanning...",
            ] if is_active else [
                "(=^.^=) watching mirrors",
                "(= -.-=) watching mirrors",
                "(=^.^=) watching mirrors",
                "(= o.o=) watching mirrors",
            ]
            if is_error:
                side_frames = ["(=>_<=) check log", "(=>_<=) check log."]
            self.side_neko_label.setText(side_frames[self.neko_frame_idx % len(side_frames)])
            
        if hasattr(self, 'search_worker') and self.search_worker and self.search_worker.isRunning():
            spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spin_idx = self.neko_frame_idx % len(spinners)
            base_text = self.search_mirror_label.text()
            if len(base_text) > 2 and base_text[0] in spinners:
                base_text = base_text[2:]
            self.search_mirror_label.setText(f"{spinners[spin_idx]} {base_text}")


    # --- Cover Preview Handlers ---
    def on_table_selection_changed(self):
        # Determine which table triggered this if we want, or just check the active tab
        idx = self.tabs.currentIndex()
        book = None
        if idx == 0:
            rows = self.get_selected_result_rows()
            if rows:
                book = self.search_results[rows[0]]
        elif idx == 1:
            rows = sorted([item.row() for item in self.queue_table.selectedItems()])
            if rows:
                row = rows[0]
                if row < len(self.queue_items):
                    book = self.queue_items[row]["book"]
        
        if book and getattr(book, "detail_url", None):
            cache_key = book.detail_url or book.title
            if cache_key in self.cover_cache:
                self.cover_cache.move_to_end(cache_key)
                if hasattr(self, 'cover_worker') and self.cover_worker and self.cover_worker.isRunning():
                    self.cover_worker.abort()
                self.cover_anim_timer.stop()
                self._display_cover_pixmap(self.cover_cache[cache_key])
                return

            if hasattr(self, 'cover_worker') and self.cover_worker and self.cover_worker.isRunning():
                self.cover_worker.abort()

            # Start smooth animated text loading indicator
            self.cover_anim_frame = 0
            self.cover_anim_timer.start(110)
            self.update_cover_animation()

            self.cover_worker = CoverFetchWorker(book, parent=self)
            self.cover_worker.cover_fetched.connect(self.on_cover_fetched)
            self.cover_worker.cover_failed.connect(self.on_cover_failed)
            self.cover_worker.start()
        else:
            if hasattr(self, 'cover_worker') and self.cover_worker and self.cover_worker.isRunning():
                self.cover_worker.abort()
            self.cover_anim_timer.stop()
            self.cover_label.clear()
            self.cover_label.setText('<div align="center" style="font-family: monospace;"><div style="font-size: 22px; margin-bottom: 6px;">(=^.^=)</div><div style="font-family: sans-serif; font-size: 12px;">Select a book to preview</div></div>')
            self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")

    def update_cover_animation(self):
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        dots = [".  ", ".. ", "...", "   "]
        self.cover_anim_frame = getattr(self, 'cover_anim_frame', 0) + 1
        spin = spinners[self.cover_anim_frame % len(spinners)]
        dot = dots[(self.cover_anim_frame // 2) % len(dots)]

        html = f"""
        <div align="center" style="font-family: sans-serif;">
            <div style="font-family: monospace; font-size: 22px; margin-bottom: 8px;">(=O.O=)</div>
            <div style="font-size: 13px; font-weight: bold;">Loading Cover{dot}</div>
            <div style="font-size: 18px; margin-top: 10px; font-family: monospace;">{spin}</div>
        </div>
        """
        self.cover_label.setText(html)
        self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")

    def _display_cover_pixmap(self, data):
        from qt.core import QPixmap
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled_pixmap = pixmap.scaled(
                self.cover_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.cover_label.clear()
            self.cover_label.setPixmap(scaled_pixmap)
            self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")
        else:
            self.on_cover_failed("")

    def on_cover_fetched(self, data, detail_url):
        if detail_url:
            self.cover_cache[detail_url] = data
            self.cover_cache.move_to_end(detail_url)
            while len(self.cover_cache) > 100:
                self.cover_cache.popitem(last=False)

        # Check if the fetched cover still matches the currently selected book
        idx = self.tabs.currentIndex()
        curr_book = None
        if idx == 0:
            rows = self.get_selected_result_rows()
            if rows:
                curr_book = self.search_results[rows[0]]
        elif idx == 1:
            rows = sorted([item.row() for item in self.queue_table.selectedItems()])
            if rows and rows[0] < len(self.queue_items):
                curr_book = self.queue_items[rows[0]]["book"]

        curr_url = getattr(curr_book, "detail_url", "")
        if curr_url == detail_url or not curr_url:
            self.cover_anim_timer.stop()
            self._display_cover_pixmap(data)

    def on_cover_failed(self, detail_url=""):
        self.cover_anim_timer.stop()
        self.cover_label.clear()
        self.cover_label.setText('<div align="center" style="font-family: monospace;"><div style="font-size: 22px; margin-bottom: 6px;">(= -.-=)</div><div style="font-family: sans-serif; font-size: 12px;">No Cover Available</div></div>')
        self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")

    def setup_search_completer(self):
        """Sets up or clears QCompleter based on whether local search history is enabled."""
        if hasattr(self, "search_input") and prefs.get("save_search_history", False):
            history = get_search_history()
            if history:
                seen = set()
                unique_hist = []
                for q in reversed(history):
                    if q not in seen:
                        seen.add(q)
                        unique_hist.append(q)
                completer = QCompleter(unique_hist, self)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                self.search_input.setCompleter(completer)
                return
        if hasattr(self, "search_input"):
            self.search_input.setCompleter(None)

    def on_history_toggled(self, state):
        if hasattr(self, "history_checkbox"):
            prefs["save_search_history"] = self.history_checkbox.isChecked()
            self.setup_search_completer()

    def open_history_settings(self):
        dlg = HistorySettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if hasattr(self, "history_checkbox"):
                self.history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
            self.setup_search_completer()

    def toggle_advanced_filters(self):
        if not hasattr(self, "advanced_filters_widget"):
            return
        new_state = not self.advanced_filters_widget.isVisible()
        self.advanced_filters_widget.setVisible(new_state)
        if hasattr(self, "toggle_filters_btn"):
            self.toggle_filters_btn.setText("⚙ Filters ▴" if new_state else "⚙ Filters ▾")
        prefs["show_advanced_filters"] = new_state

    # --- Search Handlers ---
    def start_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        append_search_history(query)
        self.setup_search_completer()
        self.search_results = []
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), "Search Results (0)")

        self.search_btn.setVisible(False)
        self.stop_search_btn.setVisible(True)
        self.stop_search_btn.setEnabled(True)
        self.stop_search_btn.setText("Stop Search")

        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(True)
            self.search_progress_bar.setRange(0, 0)
            self.search_progress_bar.setFormat(f"Searching LibGen mirrors for '{query}'...")

        self.status_label.setText(f"Searching LibGen for '{query}'...")
        self.search_mirror_label.setText(f"Connecting to LibGen mirrors for '{query}'...")

        # Update saved preferences
        field_text = self.field_combo.currentText().strip()
        field_code = SEARCH_FIELDS.get(field_text, "")
        selected_mirror = self.mirror_combo.currentText().strip()
        if selected_mirror.startswith("Auto"):
            selected_mirror = "Auto"

        prefs["search_field"] = field_text
        prefs["selected_mirror"] = selected_mirror
        prefs["preferred_languages"] = self.lang_combo.checked_items()
        prefs["preferred_language"] = ", ".join(self.lang_combo.checked_items())
        prefs["preferred_format"] = self.format_combo.currentText().strip()
        prefs["filter_mode"] = self.filter_combo.currentText().strip()
        prefs["unique_results"] = self.unique_checkbox.isChecked()

        cat_text = self.category_combo.currentText().strip()
        cat_code = CATEGORIES.get(cat_text, "")
        prefs["search_category"] = cat_text

        self.search_worker = SearchWorker(
            query=query,
            search_field=field_code,
            category=cat_code,
            selected_mirror=selected_mirror,
            language=self.lang_combo.checked_items(),
            fmt=self.format_combo.currentText().strip(),
            filter_mode=self.filter_combo.currentText().strip(),
            max_results=self.max_results_spinbox.value(),
            unique_results=self.unique_checkbox.isChecked(),
            parent=self,
        )
        self.search_worker.progress_signal.connect(self.on_search_progress)
        self.search_worker.partial_results_signal.connect(self.on_search_partial_results)
        self.search_worker.finished_signal.connect(self.on_search_finished)
        self.search_worker.error_signal.connect(self.on_search_error)
        self.search_worker.start()

    def stop_search(self):
        if hasattr(self, "search_worker") and self.search_worker and self.search_worker.isRunning():
            self.stop_search_btn.setEnabled(False)
            self.stop_search_btn.setText("Stopping...")
            self.status_label.setText("Search stopped by user.")
            self.search_mirror_label.setText("Search stopped by user.")
            self.search_worker.abort()
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)
        self.stop_search_btn.setVisible(False)
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)

    def on_search_progress(self, idx, total, mirror, found_count=0, target_count=0):
        host = urlparse(mirror).netloc or mirror
        percent = int(((idx - 1) / total) * 100) if total > 0 else 0

        if target_count > 0:
            msg = f"Querying mirrors [{idx}/{total}] • 📦 {found_count}/{target_count} artifacts found ({host})"
            self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({found_count})")
            if hasattr(self, "search_progress_bar"):
                self.search_progress_bar.setVisible(True)
                self.search_progress_bar.setRange(0, target_count)
                self.search_progress_bar.setValue(found_count)
                self.search_progress_bar.setFormat(f"Found {found_count}/{target_count} ({host})")
        else:
            msg = f"Querying mirror [{idx}/{total}]: {host} ({mirror})"
            if hasattr(self, "search_progress_bar"):
                self.search_progress_bar.setVisible(True)
                self.search_progress_bar.setRange(0, total)
                self.search_progress_bar.setValue(idx)
                self.search_progress_bar.setFormat(f"Mirror {idx}/{total}: {host}")

        self.status_label.setText(msg)
        self.status_label.setToolTip(mirror)
        self.search_mirror_label.setText(msg)

    def on_search_partial_results(self, books, mirror):
        self.search_results = list(books or [])
        self.populate_results_table()
        count = len(self.search_results)
        host = urlparse(mirror).netloc or mirror or "mirror"
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({count})")
        self.search_mirror_label.setText(f"Showing {count} live result(s) from {host}...")

    def on_search_finished(self, books, mirror_used=""):
        self.search_results = books
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)
        self.stop_search_btn.setVisible(False)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

        host = urlparse(mirror_used).netloc if mirror_used else "mirror"
        success_text = f"✓ Found {len(books)} artifacts via {host}." if mirror_used else f"✓ Found {len(books)} artifacts."
        self.status_label.setText(success_text)
        self.search_mirror_label.setText(success_text)
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(books)})")
        self.set_current_tab_widget(getattr(self, "tab_results", None))
        self.populate_results_table()

        query = self.search_input.text().strip()
        if not books and query:
            add_pending_search(query)
            self.update_pending_combo()
        elif books and query:
            remove_pending_search(query)
            self.update_pending_combo()

    def on_search_error(self, err_msg):
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)
        self.stop_search_btn.setVisible(False)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

        self.status_label.setText(f"Search failed: {err_msg}")
        self.search_mirror_label.setText(f"Search failed: {err_msg}")

        query = self.search_input.text().strip()
        if query:
            add_pending_search(query)
            self.update_pending_combo()

        QMessageBox.warning(self, "Search Error", f"Failed to search LibGen mirrors:\n{err_msg}")

    # --- Calibre Selection & Hardcover Search Queue Handlers ---
    def update_search_queue_bar(self):
        if not hasattr(self, "search_queue_bar"):
            return
        n_books = len(self.selected_books) if hasattr(self, "selected_books") and self.selected_books else 0
        if n_books > 0:
            self.queue_info_label.setText(f"📚 <b>{n_books} record(s)</b> loaded into Search Queue")
            self.start_queue_search_btn.setText(f"▶ Search All ({n_books}) Records (Max 2/book)")
            self.start_queue_search_btn.setEnabled(True)
            self.start_queue_search_btn.setVisible(True)
            self.stop_queue_search_btn.setVisible(False)
            self.search_queue_bar.setVisible(True)
        else:
            self.search_queue_bar.setVisible(False)

    def dismiss_search_queue_bar(self):
        self.selected_books = []
        if hasattr(self, "search_queue_bar"):
            self.search_queue_bar.setVisible(False)

    def start_search_queue(self):
        if not self.selected_books:
            return

        if hasattr(self, "search_queue_worker") and self.search_queue_worker and self.search_queue_worker.isRunning():
            return

        self.start_queue_search_btn.setVisible(False)
        self.stop_queue_search_btn.setVisible(True)
        self.stop_queue_search_btn.setEnabled(True)
        self.stop_queue_search_btn.setText("Stop Queue Search")
        self.search_btn.setEnabled(False)
        self.search_results = []
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), "Search Results (0)")

        total_recs = len(self.selected_books)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(True)
            self.search_progress_bar.setRange(0, total_recs)
            self.search_progress_bar.setValue(0)
            self.search_progress_bar.setFormat(f"Queue Search: 0/{total_recs} records")

        self.status_label.setText(f"Starting serialized search across {total_recs} Calibre book record(s)...")
        self.search_mirror_label.setText(f"Parallel search: 0/{total_recs} records processed")
        self.append_log(f"--- Starting Parallel Search Queue ({total_recs} books, max 2 results/book, 3 mirror lanes) ---")

        selected_mirror = self.mirror_combo.currentText().strip()
        if selected_mirror.startswith("Auto"):
            selected_mirror = "Auto"
        mirrors = get_mirrors()

        self.search_queue_worker = SearchQueueWorker(
            records=self.selected_books,
            mirrors=mirrors,
            selected_mirror=selected_mirror,
            timeout=int(prefs.get("timeout", 20)),
            language=self.lang_combo.checked_items(),
            fmt=self.format_combo.currentText().strip(),
            filter_mode=self.filter_combo.currentText().strip(),
            unique_results=self.unique_checkbox.isChecked(),
            parent=self,
        )
        self.search_queue_worker.progress_signal.connect(self.on_search_queue_progress)
        self.search_queue_worker.record_finished_signal.connect(self.on_search_queue_record_finished)
        self.search_queue_worker.finished_signal.connect(self.on_search_queue_finished)
        self.search_queue_worker.start()

    def stop_search_queue(self):
        if hasattr(self, "search_queue_worker") and self.search_queue_worker and self.search_queue_worker.isRunning():
            self.stop_queue_search_btn.setEnabled(False)
            self.stop_queue_search_btn.setText("Stopping...")
            self.status_label.setText("Stopping serialized search queue...")
            self.search_queue_worker.abort()
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

    def on_search_queue_progress(self, idx, total, title, status_msg):
        self.status_label.setText(f"[{idx}/{total}] {status_msg}")
        self.search_mirror_label.setText(f"Batch Search [{idx}/{total}]: {title}")
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(True)
            self.search_progress_bar.setRange(0, total)
            self.search_progress_bar.setValue(idx)
            self.search_progress_bar.setFormat(f"Record {idx}/{total}: {title[:32]}")
        self.append_log(f"[Search Queue] {status_msg}")

    def on_search_queue_record_finished(self, record_info, matched_books):
        added = 0
        for book in matched_books or []:
            if not any(getattr(existing, "detail_url", None) == book.detail_url for existing in self.search_results):
                self.search_results.append(book)
                added += 1
        if added:
            self.populate_results_table()
            count = len(self.search_results)
            self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({count})")
            title = record_info.get("title", "") if isinstance(record_info, dict) else ""
            self.search_mirror_label.setText(f"Added {added} live result(s): {title[:48]}")

    def on_search_queue_finished(self, all_results, matched_cnt, failed_cnt):
        self.start_queue_search_btn.setVisible(True)
        self.start_queue_search_btn.setEnabled(True)
        self.stop_queue_search_btn.setVisible(False)
        self.search_btn.setEnabled(True)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

        self.search_results = all_results
        self.populate_results_table()
        # Highlight/select all rows so user can easily review and click 'Add to Queue' or deselect
        self.results_table.selectAll()

        msg = f"✓ Found {len(all_results)} match(es) across {matched_cnt} of {len(self.selected_books)} record(s)."
        if failed_cnt > 0:
            msg += f" ({failed_cnt} with 0 matches added to Pending)"
        self.status_label.setText(msg)
        self.search_mirror_label.setText(msg)
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(all_results)})")
        self.set_current_tab_widget(getattr(self, "tab_results", None))

        self.append_log(f"--- Parallel Search Complete: {len(all_results)} match(es) ready for review in Search Results ---")
        self.append_log("Select desired books in Search Results and click 'Add to Queue' (Ctrl+Shift+A).")

        QMessageBox.information(
            self,
            "Parallel Search Complete",
            f"Parallel search finished!\n\n"
            f"• Records searched: {len(self.selected_books)}\n"
            f"• Matched records: {matched_cnt}\n"
            f"• Total artifacts found: {len(all_results)}\n"
            f"• Zero matches: {failed_cnt}\n\n"
            "All found books have been loaded into Search Results table.\n"
            "Select the books you want and click 'Add to Queue' to queue them for download."
        )

    def populate_results_table(self):
        books = self.search_results
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(books))
        for row, book in enumerate(books):
            title_item = QTableWidgetItem(book.title)
            title_item.setData(Qt.ItemDataRole.UserRole, row)  # Store original index
            if hasattr(book, "calibre_source") and book.calibre_source:
                title_item.setToolTip(f"Matched from Calibre: {book.calibre_source}")
            self.results_table.setItem(row, 0, title_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(book.author))
            pub_year = f"{book.publisher} ({book.year})".strip(" ()")
            self.results_table.setItem(row, 2, QTableWidgetItem(pub_year))
            self.results_table.setItem(row, 3, QTableWidgetItem(book.language))
            self.results_table.setItem(row, 4, QTableWidgetItem(book.extension))
            self.results_table.setItem(row, 5, SizeTableWidgetItem(book.size))
        self.results_table.setSortingEnabled(True)

    def select_all_results(self):
        self.results_table.selectAll()

    def deselect_all_results(self):
        self.results_table.clearSelection()

    def discard_selected_results(self):
        selected_rows = set(self.get_selected_result_rows())
        if not selected_rows:
            QMessageBox.information(self, "No Items Selected", "Please select one or more books in the results table.")
            return

        self.search_results = [
            book for idx, book in enumerate(self.search_results)
            if idx not in selected_rows
        ]
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(self.search_results)})")
        self.status_label.setText(f"Discarded {len(selected_rows)} selected search result(s).")
        self.search_input.setFocus()

    def get_selected_result_rows(self):
        # Extract the original index from UserRole instead of using the sorted row index
        selected_rows = set()
        for idx in self.results_table.selectedIndexes():
            item = self.results_table.item(idx.row(), 0)
            if item is not None:
                orig_idx = item.data(Qt.ItemDataRole.UserRole)
                if orig_idx is not None:
                    selected_rows.add(orig_idx)
        return sorted(list(selected_rows))

    def show_results_context_menu(self, pos):
        selected_rows = self.get_selected_result_rows()
        if not selected_rows:
            return

        menu = QMenu(self)
        count = len(selected_rows)
        add_act = menu.addAction(f"Add Selected ({count}) to Queue\tCtrl+Shift+A")
        add_act.triggered.connect(self.queue_selected_results)
        dl_act = menu.addAction(f"Download Selected ({count})")
        dl_act.triggered.connect(self.download_selected_now)
        discard_act = menu.addAction(f"Discard Selected ({count})")
        discard_act.triggered.connect(self.discard_selected_results)
        menu.exec(self.results_table.viewport().mapToGlobal(pos))

    # --- Queue Handlers ---
    def queue_selected_results(self):
        selected_rows = self.get_selected_result_rows()
        if not selected_rows:
            QMessageBox.information(self, "No Items Selected", "Please select one or more books in the results table.")
            return

        added_count = 0
        queued_urls = set()
        for r in selected_rows:
            if r < len(self.search_results):
                book = self.search_results[r]
                # Avoid duplicates in queue
                if not any(q["book"].detail_url == book.detail_url for q in self.queue_items):
                    self.queue_items.append({
                        "book": book,
                        "status": "Queued",
                    })
                    added_count += 1
                queued_urls.add(book.detail_url)

        # Immediately remove queued items from search results
        if queued_urls:
            self.search_results = [b for b in self.search_results if b.detail_url not in queued_urls]
            self.populate_results_table()
            self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(self.search_results)})")

        self.update_queue_table()
        if added_count > 0:
            self.status_label.setText(f"Added {added_count} book(s) to Queue.")
        else:
            self.status_label.setText("Selected book(s) already in Queue.")

        # Retain focus directly in the search input
        self.search_input.setFocus()
        self.search_input.selectAll()

    def download_selected_now(self):
        self.queue_selected_results()
        self.start_bulk_download()

    def save_queue(self):
        saved = []
        for q in self.queue_items:
            bk = q.get("book")
            if bk:
                saved.append({
                    "book": serialize_book(bk),
                    "status": q.get("status", "Queued"),
                    "progress": q.get("progress", 0),
                    "dest_file": q.get("dest_file", ""),
                    "download_timestamp": q.get("download_timestamp", 0),
                })
        prefs["saved_queue_items"] = saved

    def load_queue(self):
        self.queue_items = []
        saved = prefs.get("saved_queue_items", [])
        if not isinstance(saved, list):
            return

        now = time.time()
        retention_days = int(prefs.get("history_retention_days", 30))
        max_downloads = int(prefs.get("max_download_history", 50))
        cutoff = (now - (retention_days * 86400)) if retention_days > 0 else 0

        dl_count = 0
        valid_items = []

        for item in reversed(saved):
            b_dict = item.get("book")
            if not (b_dict and isinstance(b_dict, dict)):
                continue
            status = item.get("status", "Queued")
            is_dl = "downloaded" in status.lower() or "added" in status.lower()
            dl_ts = item.get("download_timestamp", 0)

            if is_dl:
                if cutoff > 0 and dl_ts > 0 and dl_ts < cutoff:
                    continue
                if dl_count >= max_downloads:
                    continue
                dl_count += 1

            valid_items.append({
                "book": deserialize_book(b_dict),
                "status": status,
                "progress": item.get("progress", 0),
                "dest_file": item.get("dest_file", ""),
                "download_timestamp": dl_ts,
            })

        valid_items.reverse()
        self.queue_items = valid_items
        if self.queue_items:
            self.update_queue_table()

    def _set_queue_item_progress(self, row, percent, status_text=None):
        if row >= self.queue_table.rowCount():
            return
        item = self.queue_table.item(row, 6)
        if not item:
            item = QTableWidgetItem(f"{percent}%")
            self.queue_table.setItem(row, 6, item)
        item.setData(Qt.ItemDataRole.UserRole, int(percent))
        if status_text is not None:
            item.setData(Qt.ItemDataRole.UserRole + 1, str(status_text))
        item.setText(f"{percent}%")

    def toggle_activity_log(self, force_open=False):
        if not hasattr(self, "log_view"):
            return
        show = True if force_open else (not self.log_view.isVisible())
        self.log_view.setVisible(show)
        if hasattr(self, "log_toggle_btn"):
            self.log_toggle_btn.setText("▼ Live Activity Log" if show else "▶ Live Activity Log")

    def update_queue_table(self):
        self.queue_table.setUpdatesEnabled(False)
        try:
            self.queue_table.setRowCount(len(self.queue_items))
            for row, q in enumerate(self.queue_items):
                book = q["book"]
                self.queue_table.setItem(row, 0, QTableWidgetItem(book.title))
                self.queue_table.setItem(row, 1, QTableWidgetItem(book.author))
                self.queue_table.setItem(row, 2, QTableWidgetItem(book.extension))
                self.queue_table.setItem(row, 3, QTableWidgetItem(book.size))
                status_text = q.get("status", "Queued")
                status_item = QTableWidgetItem(status_text)
                st_lower = status_text.lower()
                if "failed" in st_lower or "error" in st_lower or "skipped" in st_lower:
                    status_item.setForeground(QColor("#ef4444"))
                elif "downloaded" in st_lower or "added" in st_lower:
                    status_item.setForeground(QColor("#22c55e"))
                self.queue_table.setItem(row, 4, status_item)
                self.queue_table.setItem(row, 5, QTableWidgetItem(""))
                pct = q.get("progress", 0)
                self._set_queue_item_progress(row, pct, status_text)
    
            remaining = sum(
                1 for q in self.queue_items
                if q.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")
            )
            total = len(self.queue_items)
            if 0 < remaining < total:
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)")
            else:
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({total})")
            self._schedule_filter()
            self.save_queue()
        finally:
            self.queue_table.setUpdatesEnabled(True)

    def set_queue_filter(self, mode):
        self.queue_filter_mode = mode
        if hasattr(self, "queue_filter_btns"):
            for m, btn in self.queue_filter_btns.items():
                btn.setChecked(m == mode)
                if m == mode:
                    btn.setStyleSheet(FILTER_BUTTON_ACTIVE_STYLE)
                else:
                    btn.setStyleSheet(FILTER_BUTTON_STYLE)
        self._schedule_filter()

    def _schedule_filter(self):
        if hasattr(self, "_filter_timer") and not self._filter_timer.isActive():
            self._filter_timer.start()

    def apply_queue_filter(self):
        if not hasattr(self, "queue_table") or not hasattr(self, "queue_items"):
            return

        queued_cnt = 0
        dl_cnt = 0
        downloaded_cnt = 0
        failed_cnt = 0

        for row, q in enumerate(self.queue_items):
            status = str(q.get("status", "")).lower()
            is_downloaded = "downloaded" in status or "added" in status
            is_queued = "queued" in status and not is_downloaded
            is_dl = (
                "downloading" in status
                or "resolving" in status
                or "streaming" in status
                or "piece-together" in status
            ) and not is_downloaded
            is_failed = (
                "failed" in status
                or "error" in status
                or "skipped" in status
            ) and not is_downloaded

            if is_queued:
                queued_cnt += 1
            elif is_dl:
                dl_cnt += 1
            elif is_downloaded:
                downloaded_cnt += 1
            elif is_failed:
                failed_cnt += 1

            if getattr(self, "queue_filter_mode", "Queued") == "Queued":
                hide = not is_queued
            elif self.queue_filter_mode == "Downloading":
                hide = not is_dl
            elif self.queue_filter_mode == "Downloaded":
                hide = not is_downloaded
            elif self.queue_filter_mode == "Failed":
                hide = not is_failed
            else:
                hide = False

            self.queue_table.setRowHidden(row, hide)

        if hasattr(self, "queue_filter_btns"):
            if "Queued" in self.queue_filter_btns:
                self.queue_filter_btns["Queued"].setText(f"Queued ({queued_cnt})")
            if "Downloading" in self.queue_filter_btns:
                self.queue_filter_btns["Downloading"].setText(f"Downloading ({dl_cnt})")
            if "Downloaded" in self.queue_filter_btns:
                self.queue_filter_btns["Downloaded"].setText(f"Downloaded ({downloaded_cnt})")
            if "Failed" in self.queue_filter_btns:
                self.queue_filter_btns["Failed"].setText(f"Failed ({failed_cnt})")

    def clear_downloaded_items(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return
        self.queue_items = [
            q for q in self.queue_items
            if not ("downloaded" in str(q.get("status", "")).lower() or "added" in str(q.get("status", "")).lower())
        ]
        self.update_queue_table()

    def remove_from_queue(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return
        selected_rows = sorted(set(idx.row() for idx in self.queue_table.selectedIndexes()), reverse=True)
        for r in selected_rows:
            del self.queue_items[r]
        self.update_queue_table()

    def clear_queue(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return
        self.queue_items.clear()
        self.session_target_indices = []
        if hasattr(self, "bulk_progress_bar"):
            self.bulk_progress_bar.setVisible(False)
        self.update_queue_table()

    # --- Mirrors & Health Handlers ---
    def populate_mirrors_table(self):
        mirrors = get_mirrors()
        primary = prefs.get("primary_mirror", "https://libgen.li").strip().rstrip("/")
        custom = [m.rstrip("/") for m in prefs.get("custom_mirrors", [])]

        self.mirrors_table.setRowCount(0)
        for row, m in enumerate(mirrors):
            self.mirrors_table.insertRow(row)

            # URL
            self.mirrors_table.setItem(row, 0, QTableWidgetItem(m))

            # Health Info: (is_ok, ms, kb_s, speed_str, msg)
            health = self.mirror_health.get(m)
            if health:
                is_ok, ms, kb_s, speed_str, msg = health
                status_item = QTableWidgetItem("Online" if is_ok else "Error")
                status_item.setForeground(QColor("green") if is_ok else QColor("red"))
                latency_item = QTableWidgetItem(f"{ms} ms" if is_ok else "-")
                speed_item = QTableWidgetItem(speed_str if is_ok else "-")
            else:
                saved_latencies = prefs.get("mirror_latencies", {})
                saved_ms = saved_latencies.get(m) if isinstance(saved_latencies, dict) else None
                status_item = QTableWidgetItem("Ready" if saved_ms else "Untested")
                status_item.setForeground(QColor("gray"))
                latency_item = QTableWidgetItem(f"{saved_ms} ms" if saved_ms else "-")
                speed_item = QTableWidgetItem("-")

            self.mirrors_table.setItem(row, 1, status_item)
            self.mirrors_table.setItem(row, 2, latency_item)
            self.mirrors_table.setItem(row, 3, speed_item)

            # Type
            m_type = "Primary" if m == primary else ("Custom" if m in custom else "Fallback")
            type_item = QTableWidgetItem(m_type)
            self.mirrors_table.setItem(row, 4, type_item)

            # Action
            if m in custom:
                del_btn = QPushButton("Remove")
                del_btn.clicked.connect(lambda checked, url=m: self.remove_mirror_handler(url))
                self.mirrors_table.setCellWidget(row, 5, del_btn)
            elif health and not is_ok:
                discard_btn = QPushButton("Discard")
                discard_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
                discard_btn.setToolTip("Discard this dead mirror from your configured mirrors")
                discard_btn.clicked.connect(lambda checked, url=m: self.discard_single_mirror_handler(url))
                self.mirrors_table.setCellWidget(row, 5, discard_btn)
            else:
                self.mirrors_table.setItem(row, 5, QTableWidgetItem("-"))

    def test_all_mirrors(self):
        mirrors = get_mirrors()
        self.test_all_mirrors_btn.setEnabled(False)
        self.status_label.setText("Testing latency and download bandwidth for all LibGen mirrors...")

        self.health_worker = MirrorHealthWorker(mirrors, parent=self)
        self.health_worker.mirrors_discovered.connect(self.on_mirrors_discovered)
        self.health_worker.mirror_tested.connect(self.on_mirror_tested)
        self.health_worker.all_tested.connect(self.on_all_mirrors_tested)
        self.health_worker.start()

    def on_mirrors_discovered(self, live_mirrors):
        fallback_str = prefs.get("fallback_mirrors", "")
        fallbacks = [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip()]
        added = False
        for m in live_mirrors:
            if m not in fallbacks:
                fallbacks.append(m)
                added = True
        
        if added:
            prefs["fallback_mirrors"] = ", ".join(fallbacks)
            self.populate_mirrors_table()

    def on_mirror_tested(self, url, is_ok, ms, kb_s, speed_str, msg):
        self.mirror_health[url] = (is_ok, ms, kb_s, speed_str, msg)
        if is_ok and ms > 0:
            record_mirror_latency(url, ms)
        self.populate_mirrors_table()
        
        host = urlparse(url).netloc or url
        status = "OK" if is_ok else "FAIL"
        speed = f"{speed_str}" if is_ok else ""
        self.side_mirror_status.appendPlainText(f"[{status}] {host} {speed}")

    def on_all_mirrors_tested(self):
        self.test_all_mirrors_btn.setEnabled(True)
        self.update_mirror_combobox()
        self.populate_mirrors_table()
        self.status_label.setText("Mirror speed and latency testing completed. Mirrors sorted by latency.")

    def sort_mirrors_by_speed(self):
        """Sorts mirrors by highest bandwidth and lowest latency."""
        mirrors = get_mirrors()
        if not mirrors:
            return

        def speed_key(m):
            health = self.mirror_health.get(m)
            if not health:
                return (-1.0, -999999)
            is_ok, ms, kb_s, speed_str, msg = health
            if not is_ok:
                return (-1.0, -999999)
            return (kb_s, -ms)

        sorted_mirrors = sorted(mirrors, key=speed_key, reverse=True)
        set_mirror_order(sorted_mirrors)
        self.populate_mirrors_table()
        self.update_mirror_combobox()

        fastest = sorted_mirrors[0]
        health = self.mirror_health.get(fastest)
        if health and health[0]:
            self.status_label.setText(
                f"Sorted by speed! Fastest: {fastest} ({health[3]}, {health[1]} ms)"
            )
        else:
            self.status_label.setText("Mirrors sorted by speed.")

    def set_selected_mirror_primary(self):
        selected_rows = list(set(idx.row() for idx in self.mirrors_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(self, "Selection Required", "Please select a mirror in the table to set as primary.")
            return

        row = selected_rows[0]
        url = self.mirrors_table.item(row, 0).text().strip()
        prefs["primary_mirror"] = url
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Primary mirror updated to {url}.")

    def add_custom_mirror_handler(self):
        url = self.add_mirror_input.text().strip()
        if not url:
            return

        added_url = add_custom_mirror(url)
        if not added_url:
            QMessageBox.warning(self, "Invalid Mirror", "Please enter a LibGen mirror URL such as https://libgen.me.")
            return
        self.add_mirror_input.clear()
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Added custom mirror: {added_url}")

        # Test new mirror immediately in background
        scraper = LibgenScraper(timeout=8)
        is_ok, ms, kb_s, speed_str, msg = scraper.ping_mirror(added_url, timeout=8)
        self.mirror_health[added_url] = (is_ok, ms, kb_s, speed_str, msg)
        self.populate_mirrors_table()

    def remove_mirror_handler(self, url):
        remove_custom_mirror(url)
        if url in self.mirror_health:
            del self.mirror_health[url]
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Removed mirror: {url}")

    def discard_single_mirror_handler(self, url):
        discard_mirrors([url])
        if url in self.mirror_health:
            del self.mirror_health[url]
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Discarded dead mirror: {url}")
        self.append_log(f"🗑 Discarded dead mirror from configuration: {url}")

    def discard_dead_mirrors(self):
        """Discards all mirrors that failed the health test from the user's mirror list."""
        if not self.mirror_health:
            QMessageBox.information(
                self,
                "Test Required",
                "No health tests have been run yet.\n\nPlease click 'Ping / Test All Mirrors' first to detect dead mirrors."
            )
            return

        dead = [m for m, health in self.mirror_health.items() if health and not health[0]]
        if not dead:
            QMessageBox.information(
                self,
                "No Dead Mirrors",
                "All tested mirrors are currently online! None were discarded."
            )
            return

        dead_list_str = "\n".join(f"• {m}" for m in dead)
        reply = QMessageBox.question(
            self,
            "Discard Dead Mirrors",
            f"The following {len(dead)} mirror(s) failed the health test:\n\n{dead_list_str}\n\n"
            "Discard these dead mirrors from your configured mirrors?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        discard_mirrors(dead)
        for m in dead:
            if m in self.mirror_health:
                del self.mirror_health[m]

        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Discarded {len(dead)} dead mirror(s).")
        self.append_log(f"🗑 Discarded {len(dead)} dead mirror(s) from local configuration.")

    def set_search_query(self, query, field="Author", reset_filters_to_default=True):
        """Pre-fills search query, sets field dropdown to Author, and resets other filters to defaults."""
        self.search_input.setText(query)
        idx = self.field_combo.findText(field)
        if idx >= 0:
            self.field_combo.setCurrentIndex(idx)

        if reset_filters_to_default:
            l_idx = self.lang_combo.findText("Any")
            if l_idx >= 0:
                self.lang_combo.setCurrentIndex(l_idx)

            fmt_idx = self.format_combo.findText("Any")
            if fmt_idx >= 0:
                self.format_combo.setCurrentIndex(fmt_idx)

            m_idx = self.mirror_combo.findText("Auto (Best Latency)")
            if m_idx >= 0:
                self.mirror_combo.setCurrentIndex(m_idx)

            fil_idx = self.filter_combo.findText("Prioritize")
            if fil_idx >= 0:
                self.filter_combo.setCurrentIndex(fil_idx)

            c_idx = self.category_combo.findText("All Categories")
            if c_idx >= 0:
                self.category_combo.setCurrentIndex(c_idx)

        if query:
            self.start_search()


    def append_log(self, text):
        """Appends a timestamped message to the scrolling activity log and auto-scrolls to bottom."""
        if hasattr(self, "log_view") and self.log_view is not None:
            self.log_view.appendPlainText(text)
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def get_download_directory(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "callib")
        raw_dir = prefs.get("download_directory", default_dir) or default_dir
        return os.path.abspath(os.path.expanduser(raw_dir))

    def choose_download_directory(self):
        current_dir = self.get_download_directory()
        selected = QFileDialog.getExistingDirectory(self, "Choose Download Folder", current_dir)
        if selected:
            prefs["download_directory"] = selected
            self.status_label.setText(f"Download folder: {selected}")
            self.save_all_field_preferences()

    def ensure_download_directory(self):
        download_dir = self.get_download_directory()
        try:
            os.makedirs(download_dir, exist_ok=True)
            probe_path = os.path.join(download_dir, ".libgen-write-test")
            with open(probe_path, "w") as f:
                f.write("ok")
            os.remove(probe_path)
        except Exception as e:
            raise Exception(f"Download folder is not writable: {download_dir} ({e})")
        prefs["download_directory"] = download_dir
        return download_dir

    def retry_failed_downloads(self):
        """Finds all failed books in the queue and restarts bulk download with multi-mirror failover."""
        failed_indices = []
        for idx, item in enumerate(self.queue_items):
            status = item.get("status", "").lower()
            if "fail" in status or status == "failed" or "stop" in status:
                item["status"] = "Queued"
                item["progress"] = 0
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Queued"))
                self.queue_table.setItem(idx, 5, QTableWidgetItem("-"))
                self._set_queue_item_progress(idx, 0, "Queued")
                failed_indices.append(idx)

        if not failed_indices:
            QMessageBox.information(self, "No Failed Downloads", "There are no failed items in the queue to retry.")
            return

        # Explicitly reset the session download counter
        self.session_target_indices = list(failed_indices)
        self.session_total = len(failed_indices)
        self.session_completed = 0
        self.status_label.setText(f"0/{self.session_total} downloaded (Retrying {self.session_total} failed)")

        self.append_log(f"🔄 Retrying {len(failed_indices)} failed book(s), cycling mirrors by best latency...")
        self.start_bulk_download(target_indices=failed_indices)

    # --- Bulk Download Handlers ---
    def start_bulk_download(self, target_indices=None):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "A download is already running. Please wait or stop it first.")
            return
        
        import time
        self.bulk_start_time = time.time()

        if target_indices is not None and not isinstance(target_indices, bool):
            self.session_target_indices = list(target_indices)
        else:
            self.session_target_indices = [
                idx for idx, q in enumerate(self.queue_items) 
                if q.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")
            ]

        if not self.session_target_indices:
            QMessageBox.information(self, "Queue Empty", "No pending books in download queue.")
            return

        self.session_total = len(self.session_target_indices)
        self.session_completed = 0
        remaining = self.session_total

        self.start_download_btn.setVisible(False)
        self.stop_download_btn.setVisible(True)
        self.stop_download_btn.setEnabled(True)
        self.stop_download_btn.setText("Stop Download")
        self.status_label.setText(f"0/{self.session_total} downloaded ({remaining} remaining)")
        self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)")
        self.append_log(f"--- Starting Bulk Download: {remaining} remaining item(s) ---")

        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(False)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(False)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(False)

        if hasattr(self, "bulk_progress_bar"):
            self.bulk_progress_bar.setVisible(True)
            self.bulk_progress_bar.setMaximum(self.session_total)
            self.bulk_progress_bar.setValue(0)
            self.bulk_progress_bar.setFormat(f"Bulk Download: 0/{self.session_total} books (0%)")

        do_auto_retry = False
        if hasattr(self, 'auto_retry_checkbox'):
            do_auto_retry = self.auto_retry_checkbox.isChecked()

        do_fast_mode = False
        if hasattr(self, 'fast_mode_checkbox'):
            do_fast_mode = self.fast_mode_checkbox.isChecked()

        try:
            download_dir = self.ensure_download_directory()
        except Exception as e:
            QMessageBox.warning(self, "Download Folder Error", str(e))
            self.start_download_btn.setVisible(True)
            self.start_download_btn.setEnabled(True)
            self.stop_download_btn.setVisible(False)
            return

        action = self.download_action_combo.currentText().strip() if hasattr(self, "download_action_combo") else "Import to Calibre"
        prefs["download_action"] = action
        prefs["download_directory"] = download_dir
        self.append_log(f"Saving downloads to: {download_dir}")

        self.download_worker = BulkDownloadWorker(
            self.queue_items,
            auto_retry=do_auto_retry,
            fast_mode=do_fast_mode,
            download_dir=download_dir,
            parent=self,
        )
        self.download_worker.item_status.connect(self.on_item_status)
        self.download_worker.item_progress.connect(self.on_item_progress)
        self.download_worker.log_message.connect(self.append_log)
        self.download_worker.link_trying.connect(self.on_link_trying)
        self.download_worker.all_done.connect(self.on_bulk_all_done)
        self.download_worker.start()

    def stop_bulk_download(self):
        if self.download_worker and self.download_worker.isRunning():
            self.stop_download_btn.setEnabled(False)
            self.stop_download_btn.setText("Stopping...")
            self.status_label.setText("Stopping downloads...")
            self.append_log("⚠ Download stop requested by user. Aborting...")
            self.download_worker.abort()
        else:
            self.stop_download_btn.setVisible(False)
            self.stop_download_btn.setText("Stop Download")
            self.stop_download_btn.setEnabled(True)
            self.start_download_btn.setVisible(True)
            self.start_download_btn.setEnabled(True)
        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(True)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(True)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(True)

    def on_link_trying(self, idx, url, stage):
        host = urlparse(url).netloc or url
        if stage == "resolving":
            status_text = f"Resolving ({host})..."
        elif stage == "segmented":
            status_text = f"Piece-together ({host})..."
        else:
            status_text = f"Streaming ({host})..."

        if idx < len(self.queue_items):
            self.queue_items[idx]["status"] = status_text
            self.queue_table.setItem(idx, 4, QTableWidgetItem(status_text))
            self._schedule_filter()
        
        if stage == "streaming" or stage == "segmented":
            self.side_mirror_status.appendPlainText(f"[CONN] {host}")

    def on_item_status(self, idx, status_text):
        if idx < len(self.queue_items):
            dest_path = ""
            if "|" in status_text:
                status_text, dest_path = status_text.split("|", 1)
                self.queue_items[idx]["dest_file"] = dest_path

            self.queue_items[idx]["status"] = status_text
            status_item = QTableWidgetItem(status_text)
            st_lower = status_text.lower()
            if "failed" in st_lower or "error" in st_lower or "skipped" in st_lower:
                status_item.setForeground(QColor("#ef4444"))
                self.toggle_activity_log(force_open=True)
            elif "downloaded" in st_lower or "added" in st_lower:
                status_item.setForeground(QColor("#22c55e"))
                self.queue_items[idx]["download_timestamp"] = time.time()
                bk = self.queue_items[idx].get("book")
                dest = dest_path or self.queue_items[idx].get("dest_file", "")
                if bk:
                    append_download_history(bk, dest)
            self.queue_table.setItem(idx, 4, status_item)
            self._set_queue_item_progress(idx, self.queue_items[idx].get("progress", 0), status_text)
            self._schedule_filter()
            
            # Active session download counter
            if hasattr(self, "session_target_indices") and self.session_target_indices:
                completed = sum(
                    1 for i in self.session_target_indices 
                    if i < len(self.queue_items) and self.queue_items[i].get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"]
                )
                self.session_completed = completed
                total = getattr(self, "session_total", len(self.session_target_indices))
                remaining = max(0, total - completed)
                self.status_label.setText(f"{completed}/{total} downloaded ({remaining} remaining)")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)" if remaining > 0 else f"Queue ({len(self.queue_items)})")
                if hasattr(self, "bulk_progress_bar") and total > 0:
                    self.bulk_progress_bar.setVisible(True)
                    self.bulk_progress_bar.setMaximum(total)
                    self.bulk_progress_bar.setValue(completed)
                    pct_tot = int((completed / total) * 100)
                    self.bulk_progress_bar.setFormat(f"Bulk Download: {completed}/{total} books ({pct_tot}%)")
            else:
                downloaded = sum(1 for q in self.queue_items if q.get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"])
                remaining = max(0, len(self.queue_items) - downloaded)
                self.status_label.setText(f"{downloaded}/{len(self.queue_items)} downloaded ({remaining} remaining)")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)" if remaining > 0 else f"Queue ({len(self.queue_items)})")

    def on_item_progress(self, idx, bytes_read, total_bytes, speed_kb):
        if total_bytes > 0:
            percent = int((bytes_read / total_bytes) * 100)
            if idx < len(self.queue_items):
                self.queue_items[idx]["progress"] = percent
                self._set_queue_item_progress(idx, percent, self.queue_items[idx].get("status", "Downloading"))
                self.queue_table.setItem(idx, 5, QTableWidgetItem(f"{speed_kb:.1f} KB/s"))
            
            if hasattr(self, "session_target_indices") and self.session_target_indices:
                completed = sum(
                    1 for i in self.session_target_indices 
                    if i < len(self.queue_items) and self.queue_items[i].get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"]
                )
                self.session_completed = completed
                total = getattr(self, "session_total", len(self.session_target_indices))
                remaining = max(0, total - completed)
                self.status_label.setText(f"{completed}/{total} downloaded ({remaining} remaining)")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)" if remaining > 0 else f"Queue ({len(self.queue_items)})")
                if hasattr(self, "bulk_progress_bar") and total > 0:
                    self.bulk_progress_bar.setVisible(True)
                    self.bulk_progress_bar.setMaximum(total)
                    self.bulk_progress_bar.setValue(completed)
                    pct_tot = int((completed / total) * 100)
                    self.bulk_progress_bar.setFormat(f"Bulk Download: {completed}/{total} books ({pct_tot}%) • {speed_kb:.1f} KB/s")
            else:
                downloaded = sum(1 for q in self.queue_items if q.get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"])
                remaining = max(0, len(self.queue_items) - downloaded)
                self.status_label.setText(f"{downloaded}/{len(self.queue_items)} downloaded ({remaining} remaining)")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)" if remaining > 0 else f"Queue ({len(self.queue_items)})")

    def import_books_to_library(self, file_paths):
        """Batch import downloaded books into Calibre library."""
        if not file_paths:
            return
        file_paths = [os.path.abspath(os.path.expanduser(p)) for p in file_paths if p and os.path.isfile(p)]
        if not file_paths:
            QMessageBox.warning(self, "Import Failed", "Downloaded files were not readable from the selected folder.")
            return
        try:
            if hasattr(self.gui, "iactions") and "Add Books" in self.gui.iactions:
                add_action = self.gui.iactions["Add Books"]
                if hasattr(add_action, "_add_books"):
                    add_action._add_books(file_paths, False)
                elif hasattr(add_action, "add_books"):
                    add_action.add_books(file_paths)
            else:
                from calibre.gui2.add import Adder
                Adder(file_paths, db=self.gui.current_db, parent=self.gui)
        except Exception as e:
            print(f"[LibGen Plugin] Failed to auto-import books: {e}")

    def on_bulk_all_done(self, downloaded_items, fail_count, is_aborted):
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.setText("Stop Download")
        self.stop_download_btn.setEnabled(True)
        self.start_download_btn.setVisible(True)
        self.start_download_btn.setEnabled(True)

        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(True)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(True)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(True)

        import time
        elapsed = 1
        if hasattr(self, 'bulk_start_time') and self.bulk_start_time:
            elapsed = max(1, int(time.time() - self.bulk_start_time))

        if elapsed >= 60:
            time_str = f"{elapsed // 60}m {elapsed % 60}s"
        else:
            time_str = f"{elapsed}s"

        if hasattr(self, "bulk_progress_bar"):
            total = getattr(self, "session_total", len(downloaded_items))
            self.bulk_progress_bar.setMaximum(total if total > 0 else 1)
            self.bulk_progress_bar.setValue(len(downloaded_items))
            self.bulk_progress_bar.setFormat(f"Bulk: {len(downloaded_items)}/{total} completed in {time_str}")

        # Calculate exact total bytes transferred across downloaded items
        total_bytes = 0
        for it in downloaded_items:
            fp = it.get("file_path")
            if fp and os.path.exists(fp):
                try:
                    total_bytes += os.path.getsize(fp)
                except Exception:
                    pass

        # Format transferred data size
        if total_bytes >= 1024 * 1024 * 1024:
            size_str = f"{total_bytes / (1024**3):.2f} GB"
        elif total_bytes >= 1024 * 1024:
            size_str = f"{total_bytes / (1024**2):.2f} MB"
        elif total_bytes >= 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes} B"

        # Calculate average transfer bandwidth
        if total_bytes > 0 and elapsed > 0:
            speed_b = total_bytes / elapsed
            if speed_b >= 1024 * 1024:
                speed_str = f"{speed_b / (1024**2):.2f} MB/s"
            elif speed_b >= 1024:
                speed_str = f"{speed_b / 1024:.1f} KB/s"
            else:
                speed_str = f"{speed_b:.0f} B/s"
        else:
            speed_str = "0 KB/s"

        fastest_cdns = get_fastest_cdns()
        if fastest_cdns:
            self.side_mirror_status.appendPlainText("[FASTEST CDNs] " + ", ".join(f"{h} ({s:.1f} KB/s)" for h, s in fastest_cdns[:3]))

        cdn_section = ""
        cdn_summary = ""
        if fastest_cdns:
            cdn_lines = "\n".join(f"    • {h}: {s:.1f} KB/s" for h, s in fastest_cdns[:3])
            cdn_section = f"\n  ⚡ Fastest CDNs:\n{cdn_lines}"
            cdn_summary = "\n\nFastest CDNs:\n" + "\n".join(f"• {h}: {s:.1f} KB/s" for h, s in fastest_cdns[:3])

        # Formatted statistics banner
        stats_box = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  📊 Bulk Download Statistics\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  ✓ Downloaded:    {len(downloaded_items)} item(s)\n"
            f"  ✗ Failed:        {fail_count} item(s)\n"
            f"  ⏱ Elapsed Time:  {time_str}\n"
            f"  📦 Total Data:    {size_str}\n"
            f"  ⚡ Avg Bandwidth: {speed_str}"
            f"{cdn_section}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        # Always log stats box to Live Log and side mirror status
        self.append_log(stats_box)
        self.side_mirror_status.appendPlainText(f"[STATS] {len(downloaded_items)} dl, {size_str} @ {speed_str} in {time_str}")

        stats_summary = {
            "time_str": time_str,
            "size_str": size_str,
            "speed_str": speed_str,
            "fastest_cdns": fastest_cdns,
        }

        summary_dialog_msg = (
            f"Bulk download completed.\n\n"
            f"• Downloaded:     {len(downloaded_items)} book(s)\n"
            f"• Failed:         {fail_count} book(s)\n"
            f"• Elapsed Time:   {time_str}\n"
            f"• Total Data:     {size_str}\n"
            f"• Avg Bandwidth:  {speed_str}"
            f"{cdn_summary}"
        )

        if not downloaded_items:
            if is_aborted:
                self.status_label.setText(f"Aborted ({time_str}): 0 downloaded.")
                if self.show_stats:
                    QMessageBox.information(self, "Download Aborted", f"Downloads were stopped by user.\n\n{summary_dialog_msg}")
            else:
                self.status_label.setText(f"Failed ({time_str}): {fail_count} failed.")
                if self.show_stats:
                    QMessageBox.warning(self, "Download Failed", f"All downloads failed.\n\n{summary_dialog_msg}")
            self._prompt_preserve_failed_items(fail_count)
            return

        self.status_label.setText(f"Completed: {len(downloaded_items)} downloaded ({size_str} @ {speed_str}) in {time_str}")
        if self.show_stats:
            QMessageBox.information(self, "Bulk Download Summary", summary_dialog_msg)

        action = prefs.get("download_action", "Import to Calibre")
        if action == "Save to Folder":
            download_dir = prefs.get("download_directory", self.get_download_directory())
            for it in downloaded_items:
                idx = it["index"]
                self.queue_items[idx]["status"] = "Downloaded"
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded"))
            self.status_label.setText(f"Saved {len(downloaded_items)} book(s) to {download_dir}.")
            QMessageBox.information(
                self,
                "Download Complete",
                f"Saved {len(downloaded_items)} book(s) to:\n{download_dir}"
            )
            if fail_count > 0:
                self._prompt_preserve_failed_items(fail_count)
            return

        # Present Review modal dialog to user
        review_dlg = ReviewImportDialog(downloaded_items, is_aborted=is_aborted, stats_summary=stats_summary, parent=self)
        if review_dlg.exec() == QDialog.DialogCode.Accepted and review_dlg.approved_items:
            approved = review_dlg.approved_items
            file_paths = [it["file_path"] for it in approved]
            self.import_books_to_library(file_paths)

            approved_indices = set(it["index"] for it in approved)
            for it in downloaded_items:
                idx = it["index"]
                if idx in approved_indices:
                    self.queue_items[idx]["status"] = "✓ Added to Library"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("✓ Added to Library"))
                else:
                    self.queue_items[idx]["status"] = "Downloaded (Not Imported)"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded (Not Imported)"))

            self.status_label.setText(f"Successfully added {len(approved)} book(s) to Calibre library.")
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully added {len(approved)} book(s) into your Calibre library."
            )
        else:
            for it in downloaded_items:
                idx = it["index"]
                self.queue_items[idx]["status"] = "Downloaded (Not Imported)"
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded (Not Imported)"))
            self.status_label.setText("Import skipped. Downloaded books held in queue.")

        if fail_count > 0:
            self._prompt_preserve_failed_items(fail_count)

    def _prompt_preserve_failed_items(self, fail_count):
        if fail_count <= 0:
            return
        reply = QMessageBox.question(
            self,
            "Preserve Failed Downloads?",
            f"{fail_count} download(s) could not complete or were stopped.\n\n"
            "Would you like to dump and preserve the failed downloads and partial chunks in the Queue for later retry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for idx, itm in enumerate(self.queue_items):
                st = itm.get("status", "").lower()
                if "fail" in st or "stop" in st:
                    itm["status"] = "Queued (Ready to retry)"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("Queued (Ready to retry)"))
            self.set_current_tab_widget(getattr(self, "tab_queue", None))
            self.append_log(f"↻ Preserved {fail_count} failed download(s) and chunks in Queue for later retry.")

    def save_all_field_preferences(self, *args):
        """Starts a debounce timer to persist preferences without spamming disk I/O."""
        if hasattr(self, "save_timer"):
            self.save_timer.start()

    def _do_save_all_field_preferences(self):
        """Actually persists the current values to disk."""
        if hasattr(self, "field_combo"):
            prefs["search_field"] = self.field_combo.currentText().strip()
        if hasattr(self, "category_combo"):
            prefs["search_category"] = self.category_combo.currentText().strip()
        if hasattr(self, "lang_combo"):
            langs = self.lang_combo.checked_items()
            prefs["preferred_languages"] = langs
            prefs["preferred_language"] = ", ".join(langs)
        if hasattr(self, "format_combo"):
            prefs["preferred_format"] = self.format_combo.currentText().strip()
        if hasattr(self, "filter_combo"):
            prefs["filter_mode"] = self.filter_combo.currentText().strip()
        if hasattr(self, "unique_checkbox"):
            prefs["unique_results"] = self.unique_checkbox.isChecked()
        if hasattr(self, "history_checkbox"):
            prefs["save_search_history"] = self.history_checkbox.isChecked()
        if hasattr(self, "fast_mode_checkbox"):
            prefs["fast_mode"] = self.fast_mode_checkbox.isChecked()
        if hasattr(self, "download_action_combo"):
            prefs["download_action"] = self.download_action_combo.currentText().strip()
        if hasattr(self, "download_dir_btn"):
            prefs["download_directory"] = self.get_download_directory()
        if hasattr(self, "max_results_spinbox"):
            prefs["max_results"] = self.max_results_spinbox.value()
        if hasattr(self, "mirror_combo"):
            m_text = self.mirror_combo.currentText().strip()
            if m_text.startswith("Auto"):
                m_text = "Auto"
            prefs["selected_mirror"] = m_text
        prefs["dialog_width"] = self.width()
        prefs["dialog_height"] = self.height()
        self.save_queue()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.save_all_field_preferences()

    def closeEvent(self, event):
        # Stop all timers
        for timer_name in ['save_timer', 'neko_timer', 'cover_anim_timer', 'version_click_timer']:
            t = getattr(self, timer_name, None)
            if t:
                t.stop()

        self._do_save_all_field_preferences()
        self.save_header_states()

        # Handle UI confirmation if downloading
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Download Running",
                "Downloads are in progress. Stop downloads and review completed books?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Abort and wait all workers
        for worker_attr in ['search_worker', 'search_queue_worker', 
                            'cover_worker', 'health_worker', 
                            'live_mirror_worker', 'download_worker']:
            w = getattr(self, worker_attr, None)
            if w and w.isRunning():
                w.abort()
                w.wait(2000)

        event.accept()
