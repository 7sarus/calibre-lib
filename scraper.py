#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Core HTML scraping and mirror management for LibGen.
"""

import os
import re
import time
import shutil
import threading
import concurrent.futures
from contextlib import contextmanager
from urllib.parse import urljoin, quote_plus, urlparse
from bs4 import BeautifulSoup
from calibre import browser

# Use lxml if available (2-4× faster parsing), fall back to html.parser
try:
    import lxml  # noqa: F401
    HTML_PARSER = "lxml"
except ImportError:
    HTML_PARSER = "html.parser"

# Thread-local storage for browser instance reuse
_thread_local = threading.local()

# Precompiled regex patterns — avoids recompilation on every book row
_RE_NONWORD = re.compile(r'[\W_]+')
_RE_BRACKETS = re.compile(r'\[.*?\]|\(.*?\)')
_RE_MD5 = re.compile(r'(?i)(?:md5=|[/\\])([a-f0-9]{32})\b')
_RE_WORD = re.compile(r'\w+')
_RE_MIRROR = re.compile(r"^https?://(?:www\.)?libgen\.[a-z]{2,}(?::\d+)?/?$", re.IGNORECASE)


def _clean_mirror_url(url):
    clean = (url or "").strip().rstrip("/")
    if not clean:
        return ""
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    if not _RE_MIRROR.match(clean):
        return ""
    return clean.lower()


class LibgenBook:
    def __init__(self):
        self.id = ""
        self.md5 = ""
        self.title = ""
        self.author = ""
        self.publisher = ""
        self.year = ""
        self.language = ""
        self.pages = ""
        self.size = ""
        self.extension = ""
        self.detail_url = ""
        self.download_url = ""
        self.cover_url = ""

    def __repr__(self):
        return f"<LibgenBook '{self.title}' by '{self.author}' [{self.extension}]>"


class LibgenScraper:
    DEFAULT_MIRRORS = [
        "https://libgen.li",
        "https://libgen.me",
        "https://libgen.vg",
        "https://libgen.gl",
        "https://libgen.bz",
        "https://libgen.la",
        "https://libgen.is",
    ]

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
    )

    @staticmethod
    def fetch_live_mirrors():
        """Fetches active LibGen mirrors from open-slum.org tracker."""
        import urllib.request
        import re
        mirrors = set()
        try:
            req = urllib.request.Request("https://open-slum.org/libgen.html", headers={"User-Agent": LibgenScraper.USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")
                # find all <a ... href="https://libgen.*"...>
                matches = re.findall(r'href="(https://libgen\.[a-z]+)"', html, re.IGNORECASE)
                for m in matches:
                    mirrors.add(m.lower())
        except Exception:
            pass
        return list(mirrors)

    def __init__(self, mirrors=None, timeout=20):
        cleaned = [_clean_mirror_url(m) for m in (mirrors or self.DEFAULT_MIRRORS)]
        self.mirrors = [m for m in cleaned if m] or list(self.DEFAULT_MIRRORS)
        self.timeout = timeout
        self._mirror_cooldowns = {}  # mirror -> (fail_count, next_retry_time)

    def _is_cooled_down(self, mirror):
        if mirror not in self._mirror_cooldowns:
            return True
        fails, next_retry = self._mirror_cooldowns[mirror]
        return time.monotonic() >= next_retry

    def _record_failure(self, mirror):
        fails = self._mirror_cooldowns.get(mirror, (0, 0))[0] + 1
        delay = min(2 ** fails, 60)
        self._mirror_cooldowns[mirror] = (fails, time.monotonic() + delay)

    @contextmanager
    def _open_url(self, browser, url_or_req, timeout=None):
        resp = browser.open(url_or_req, timeout=timeout) if timeout else browser.open(url_or_req)
        try:
            yield resp
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _get_browser(self):
        """Returns a thread-local cached browser instance for connection reuse."""
        import ssl
        b = getattr(_thread_local, "browser", None)
        if b is None:
            b = browser()
            b.set_handle_robots(False)
            b.set_handle_refresh(False)
            b.set_handle_equiv(False)
            
            # Disable SSL verification for shady mirrors
            try:
                context = ssl._create_unverified_context()
                import urllib.request
                import mechanize
                b.set_ca_data(context=context)
            except Exception:
                pass
            
            b.addheaders = [("User-Agent", self.USER_AGENT)]
            _thread_local.browser = b
        return b

    def search(
        self,
        query,
        search_field="",
        category="",
        selected_mirror=None,
        max_results=5,
        preferred_language="Any",
        preferred_format="Any",
        filter_mode="Prioritize",
        unique_results=True,
        progress_callback=None,
        partial_results_callback=None,
        abort_check=None,
        auto_field_fallback=True,
    ):
        """
        Search LibGen mirrors concurrently for books matching the query.
        First mirror to return results wins; all others are cancelled.
        Includes automatic cascade fallback to 'All Fields' if a specific field yields no results.
        """

        encoded_query = quote_plus(query.strip())

        # Determine mirror order: selected mirror first (if valid), followed by remaining mirrors
        mirror_order = list(self.mirrors)
        if selected_mirror and selected_mirror != "Auto":
            clean_selected = selected_mirror.strip().rstrip("/")
            mirror_order = [clean_selected] + [m for m in mirror_order if m.rstrip("/") != clean_selected]

        clean_mirrors = []
        seen_mirrors = set()
        for mirror in mirror_order:
            clean = mirror.strip().rstrip("/") if mirror else ""
            if clean and clean not in seen_mirrors:
                clean_mirrors.append(clean)
                seen_mirrors.add(clean)
        total_mirrors = len(clean_mirrors)
        if total_mirrors == 0:
            return []

        # Concurrent first-result-wins: fire searches to all mirrors, return first success
        found_event = threading.Event()

        if isinstance(preferred_language, (list, tuple, set)):
            pref_langs = [str(l).strip().lower() for l in preferred_language if str(l).strip()]
        else:
            pref_langs = [l.strip().lower() for l in (preferred_language or "").split(",") if l.strip()]
        has_lang_filter = bool(pref_langs) and ("any" not in pref_langs)

        def book_matches_lang(b):
            if not has_lang_filter:
                return True
            return any(l in (b.language or "").lower() for l in pref_langs)

        # Fetch enough for filtering without forcing every normal search to parse 100+ rows.
        has_format_filter = bool(preferred_format and preferred_format != "Any")
        if has_lang_filter or has_format_filter:
            fetch_count = min(100, max(max_results * 8, 40))
        else:
            fetch_count = min(60, max(max_results * 4, 20))

        is_field_search = bool(search_field)
        field_map = {"t": "title", "a": "author", "s": "series", "p": "publisher", "y": "year", "i": "identifier"}
        classic_col = field_map.get(search_field, "def")
        modern_field_param = f"&columns%5B%5D={search_field}" if search_field else ""
        modern_topic_param = f"&topics%5B%5D={category}" if category else "&topics%5B%5D=l&topics%5B%5D=f"

        def _build_search_url(mirror):
            is_classic = any(h in mirror.lower() for h in ["libgen.is", "libgen.rs", "libgen.st"])
            if is_classic:
                return f"{mirror}/search.php?req={encoded_query}&column={classic_col}&res={fetch_count}"
            return f"{mirror}/index.php?req={encoded_query}{modern_field_param}{modern_topic_param}&res={fetch_count}"

        def _search_mirror(mirror):
            if found_event.is_set() or (abort_check and abort_check()):
                return None, mirror
            if not self._is_cooled_down(mirror):
                return None, mirror
            try:
                b = self._get_browser()
                search_url = _build_search_url(mirror)

                with self._open_url(b, search_url, timeout=self.timeout) as resp:
                    if found_event.is_set() or (abort_check and abort_check()):
                        return None, mirror
                    html = resp.read()
                    soup = BeautifulSoup(html, HTML_PARSER)
                result = self._parse_search_page(soup, mirror)
                if result:
                    self._mirror_cooldowns.pop(mirror, None)  # Reset on success
                    return result, mirror
            except Exception:
                self._record_failure(mirror)
            return None, mirror

        books = []
        collected_books = []
        winning_mirror = ""
        mirrors_done = 0
        current_match_count = 0  # Cache to avoid recomputing on mirror misses
        last_ranked_books = []
        last_matching_books = []

        def _notify_progress(mirror, current_found):
            if progress_callback:
                try:
                    progress_callback(mirrors_done, total_mirrors, mirror, current_found, max_results)
                except TypeError:
                    try:
                        progress_callback(mirrors_done, total_mirrors, mirror)
                    except Exception:
                        pass
                except Exception:
                    pass

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(total_mirrors, 5))
        try:
            futures = {pool.submit(_search_mirror, m): m for m in clean_mirrors}
            for fut in concurrent.futures.as_completed(futures):
                if abort_check and abort_check():
                    raise Exception("Search stopped by user")
                mirrors_done += 1
                curr_mirror = futures[fut]

                try:
                    candidates, mirror = fut.result()
                    if candidates:
                        if not winning_mirror:
                            winning_mirror = mirror
                            try:
                                from calibre_plugins.libgen_store.config import record_successful_mirror
                                record_successful_mirror(mirror)
                            except Exception:
                                pass

                        collected_books.extend(candidates)

                        # Filter for unique if applied
                        processed_books = self._deduplicate_books(collected_books, preferred_format) if unique_results else list(collected_books)

                        # Filter and rank based on language, format preferences, and query relevance
                        ranked_current = self._filter_and_rank(
                            processed_books,
                            preferred_language=preferred_language,
                            preferred_format=preferred_format,
                            filter_mode=filter_mode,
                            query=query,
                        )
                        matching_lang_books = [b for b in ranked_current if book_matches_lang(b)]
                        last_ranked_books = ranked_current
                        last_matching_books = matching_lang_books
                        current_match_count = len(matching_lang_books) if has_lang_filter else len(ranked_current)
                        _notify_progress(mirror, min(current_match_count, max_results))
                        if partial_results_callback:
                            preview_books = matching_lang_books if has_lang_filter else ranked_current
                            try:
                                partial_results_callback(preview_books[:max_results], mirror)
                            except Exception:
                                pass

                        # Return immediately when target number of language-matching books is found!
                        if current_match_count >= max_results:
                            found_event.set()
                            books = matching_lang_books[:max_results] if has_lang_filter else ranked_current[:max_results]
                            break
                    else:
                        # Mirror returned nothing — no new books, skip redundant recompute
                        _notify_progress(curr_mirror, min(current_match_count, max_results))
                except Exception:
                    pass

                if found_event.is_set():
                    break
        finally:
            try:
                pool.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                pool.shutdown(wait=False)

        if not books and collected_books:
            if has_lang_filter and last_matching_books:
                books = last_matching_books[:max_results]
            elif not has_lang_filter:
                books = last_ranked_books[:max_results]

        # If targeted field query (e.g. Series 's', Title 't') returned 0 language matches, cascade to All Fields
        if not books and is_field_search and auto_field_fallback:
            return self.search(
                query=query,
                search_field="",
                category=category,
                selected_mirror=selected_mirror,
                max_results=max_results,
                preferred_language=preferred_language,
                preferred_format=preferred_format,
                filter_mode=filter_mode,
                unique_results=unique_results,
                progress_callback=progress_callback,
                partial_results_callback=partial_results_callback,
                abort_check=abort_check,
                auto_field_fallback=False,
            )

        return books

    def _parse_search_page(self, soup, mirror):
        """
        Parses search result tables across LibGen Plus (#tablelibgen) and standard Libgen formats (table.c).
        """
        books = []

        # Format 1: LibGen Plus (#tablelibgen)
        table = soup.select_one("#tablelibgen tbody") or soup.select_one("#tablelibgen")
        if table:
            rows = table.find_all("tr")
            for r in rows:
                cells = r.find_all("td")
                if len(cells) < 8:
                    continue

                # Title column may have multiple child nodes / links
                title_node = cells[0]
                for tag in title_node.find_all("nobr"):
                    tag.decompose()
                title = title_node.get_text(" ", strip=True)

                author = cells[1].get_text(" ", strip=True)
                publisher = cells[2].get_text(" ", strip=True)
                year = cells[3].get_text(strip=True)
                language = cells[4].get_text(strip=True)
                pages = cells[5].get_text(strip=True)
                size = cells[6].get_text(strip=True)
                extension = cells[7].get_text(strip=True).upper()

                # Cell 8 contains mirror links (e.g. ads.php or get.php)
                detail_url = ""
                if len(cells) > 8:
                    first_link = cells[8].find("a")
                    if first_link and first_link.get("href"):
                        detail_url = urljoin(mirror, first_link["href"])

                if not title:
                    continue

                cover_url = ""
                img_node = r.find("img")
                if img_node and img_node.get("src") and "blank.png" not in img_node["src"]:
                    cover_url = urljoin(mirror, img_node["src"])

                book = LibgenBook()
                md5_m = _RE_MD5.search(detail_url)
                book.md5 = md5_m.group(1).lower() if md5_m else ""
                book.title = title
                book.author = author
                book.publisher = publisher
                book.year = year
                book.language = language
                book.pages = pages
                book.size = size
                book.extension = extension
                book.detail_url = detail_url
                book.cover_url = cover_url
                books.append(book)

            if books:
                return books

        # Format 2: Classic LibGen (<table class="c"> or table[rules="rows"])
        classic_table = soup.select_one("table.c") or soup.find("table", attrs={"rules": "rows"})
        if classic_table:
            rows = classic_table.find_all("tr")
            for r in rows:
                cells = r.find_all("td")
                if len(cells) < 9:
                    continue
                # Skip header row
                if cells[0].get_text(strip=True).upper() in ["ID", ""]:
                    continue

                author = cells[1].get_text(" ", strip=True)
                title_node = cells[2]
                title_a = title_node.find("a")
                title = title_a.get_text(" ", strip=True) if title_a else title_node.get_text(" ", strip=True)

                # Check for series prefix in <font color="green">[Series]</font>
                series_fonts = [f.get_text(strip=True) for f in title_node.find_all("font", color="green")]
                if series_fonts:
                    title = f"[{' '.join(series_fonts)}] {title}"

                publisher = cells[3].get_text(" ", strip=True)
                year = cells[4].get_text(strip=True)
                pages = cells[5].get_text(strip=True)
                language = cells[6].get_text(strip=True)
                size = cells[7].get_text(strip=True)
                extension = cells[8].get_text(strip=True).upper()

                detail_url = ""
                if len(cells) > 9:
                    m_a = cells[9].find("a")
                    if m_a and m_a.get("href"):
                        detail_url = urljoin(mirror, m_a["href"])

                if not title:
                    continue

                book = LibgenBook()
                md5_m = _RE_MD5.search(detail_url)
                book.md5 = md5_m.group(1).lower() if md5_m else ""
                book.title = title
                book.author = author
                book.publisher = publisher
                book.year = year
                book.language = language
                book.pages = pages
                book.size = size
                book.extension = extension
                book.detail_url = detail_url
                book.cover_url = ""
                books.append(book)

        return books

    def _deduplicate_books(self, books, preferred_format="Any"):
        """
        Deduplicates books using MD5, file size, and metadata fields (title, author,
        language, extension).
        - If MD5 matches an already seen book, it is an identical file across mirrors.
        - If (clean_title, clean_author, lang, extension, size) matches, it is the same
          release/file even if one mirror lacked MD5 in its URL.
        - Distinct formats (EPUB vs PDF) and distinct sizes (different scans/editions)
          are preserved.
        - Preserves the preferred format or best-filled metadata entry.
        """
        unique_books = []
        md5_map = {}   # md5 -> index in unique_books
        meta_map = {}  # meta_key -> index in unique_books
        pref_fmt = (preferred_format or "").strip().upper()

        for b in books:
            # 1. Resolve MD5
            md5 = getattr(b, "md5", "") or ""
            if not md5 and getattr(b, "detail_url", ""):
                m = _RE_MD5.search(b.detail_url)
                if m:
                    md5 = m.group(1).lower()
                    b.md5 = md5

            # 2. Build normalized meta key: title + author + lang + ext + size
            raw_title = (b.title or "").lower()
            clean_title = _RE_BRACKETS.sub('', raw_title)
            clean_title = _RE_NONWORD.sub('', clean_title)
            if not clean_title:
                clean_title = _RE_NONWORD.sub('', raw_title)

            clean_author = _RE_NONWORD.sub('', (b.author or "").lower())
            lang = (b.language or "").strip().lower()
            ext = (b.extension or "").strip().upper()
            size_key = _RE_NONWORD.sub('', (b.size or "").lower())

            meta_key = (clean_title, clean_author, lang, ext, size_key)

            # 3. Check for duplicates
            dup_idx = None
            if md5 and md5 in md5_map:
                dup_idx = md5_map[md5]
            elif meta_key in meta_map:
                dup_idx = meta_map[meta_key]

            if dup_idx is None:
                # New unique book
                idx = len(unique_books)
                unique_books.append(b)
                if md5:
                    md5_map[md5] = idx
                if clean_title:
                    meta_map[meta_key] = idx
            else:
                # Existing duplicate found
                existing = unique_books[dup_idx]
                # If incoming book matches preferred format, swap it
                if pref_fmt and pref_fmt != "ANY":
                    if b.extension == pref_fmt and existing.extension != pref_fmt:
                        unique_books[dup_idx] = b
                # Link MD5 and meta_key if previously missing
                if md5 and md5 not in md5_map:
                    md5_map[md5] = dup_idx
                if meta_key not in meta_map:
                    meta_map[meta_key] = dup_idx

        return unique_books

    def _filter_and_rank(self, books, preferred_language, preferred_format, filter_mode, query=""):
        """
        Handles multi-language and format locking/filtering:
        - Strict mode: Completely discards non-matching results (with fallback if 0 matches).
        - Prioritize mode: Surfaces matching results and query relevance to the top.
        """
        if isinstance(preferred_language, (list, tuple, set)):
            pref_langs = [str(l).strip().lower() for l in preferred_language if str(l).strip()]
        else:
            pref_langs = [l.strip().lower() for l in (preferred_language or "").split(",") if l.strip()]

        has_lang_filter = bool(pref_langs) and ("any" not in pref_langs)

        def matches_language(book):
            if not has_lang_filter:
                return True
            book_lang = (book.language or "").lower()
            return any(l in book_lang for l in pref_langs)

        pref_fmt = (preferred_format or "").strip().upper()

        if filter_mode == "Strict":
            strict_list = []
            for b in books:
                if not matches_language(b):
                    continue
                if pref_fmt and pref_fmt != "ANY":
                    if b.extension != pref_fmt:
                        continue
                strict_list.append(b)
            if strict_list:
                return strict_list
            # If strict filter eliminated all candidates, fall through to Prioritize ranking

        # Prioritize Mode: score items by language match, format match, and query relevance
        query_words = [w.lower() for w in _RE_WORD.findall(query or "") if len(w) > 2]

        def get_score(book):
            score = 0
            if has_lang_filter and matches_language(book):
                score += 1000
            if pref_fmt and pref_fmt != "ANY":
                if book.extension == pref_fmt:
                    score += 100
            # Query relevance boost
            title_lower = (book.title or "").lower()
            author_lower = (book.author or "").lower()
            for w in query_words:
                if w in title_lower:
                    score += 5
                if w in author_lower:
                    score += 3
            return score

        # Sort descending by score, maintaining original order for ties
        return sorted(books, key=get_score, reverse=True)

    def resolve_details(self, detail_url, timeout=None):
        """
        Visits the detail / ads page to retrieve the authenticated direct download URL
        and high-res cover image URL.
        """
        if not detail_url:
            return None, None

        t = timeout or self.timeout
        b = self._get_browser()
        
        # Inject dynamic Referer to bypass anti-scraper mechanisms (e.g. on libgen.li)
        parsed = urlparse(detail_url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"
        b.addheaders = [("User-Agent", self.USER_AGENT), ("Referer", referer)]
        
        try:
            with self._open_url(b, detail_url, timeout=t) as resp:
                soup = BeautifulSoup(resp.read(), HTML_PARSER)

            # Extract direct get.php link
            get_link = soup.select_one('a[href*="get.php"]')
            if not get_link:
                # Look for links containing common download text/URLs
                for a in soup.find_all("a"):
                    text = a.get_text(strip=True).upper()
                    href = a.get("href", "")
                    if text in ["GET", "CLOUDFLARE", "IPFS.IO", "PINATA", "DOWNLOAD"] and href:
                        get_link = a
                        break
                    if "library.lol/main/" in href or "libgen.me/item/detail/" in href:
                        get_link = a
                        break

            download_url = (
                urljoin(detail_url, get_link["href"]) if get_link and get_link.get("href") else None
            )

            # Removed debug HTML dump

            # Extract cover image (ignore blank.png if possible)
            cover_url = None
            for img in soup.select('img[src*="cover"], td img'):
                src = img.get("src", "")
                if src and "blank.png" not in src:
                    cover_url = urljoin(detail_url, src)
                    break

            return download_url, cover_url
        except Exception:
            return None, None

    def download_file(self, download_url, destination_path, progress_callback=None, abort_check=None):
        """
        Streams a remote file to destination_path with chunked writing.
        Calls progress_callback(bytes_read, total_bytes) on each chunk.
        """
        b = self._get_browser()
        with self._open_url(b, download_url, timeout=self.timeout * 3) as resp:
            total_bytes = 0
            try:
                total_bytes = int(resp.headers.get("Content-Length", 0))
            except (ValueError, TypeError):
                total_bytes = 0
    
            bytes_read = 0
            chunk_size = 128 * 1024  # 128 KB
            start_time = time.time()
            last_cb_time = 0.0
    
            with open(destination_path, "wb") as f:
                while True:
                    if abort_check and abort_check():
                        raise Exception("Stopped by user")
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_read += len(chunk)
                    if progress_callback:
                        now = time.time()
                        if now - last_cb_time >= 0.1 or bytes_read == total_bytes:
                            elapsed = now - start_time
                            speed_kb = (bytes_read / 1024) / elapsed if elapsed > 0 else 0
                            progress_callback(bytes_read, total_bytes, speed_kb)
                            last_cb_time = now

            if bytes_read == 0 or (total_bytes > 0 and bytes_read != total_bytes):
                raise Exception(f"Incomplete download: got {bytes_read}/{total_bytes} bytes")
            if progress_callback:
                elapsed = max(time.time() - start_time, 0.001)
                progress_callback(bytes_read, total_bytes or bytes_read, bytes_read / 1024 / elapsed)
    
            elapsed = time.time() - start_time
            if elapsed > 0 and bytes_read > 0:
                final_speed_kb = (bytes_read / 1024.0) / elapsed
                self._record_cdn_speed(download_url, final_speed_kb)
    
            return destination_path

    def _record_cdn_speed(self, stream_url, speed_kb):
        host = urlparse(stream_url or "").netloc
        if not host or speed_kb <= 0:
            return
        try:
            from calibre_plugins.libgen_store.config import record_cdn_speed
            record_cdn_speed(host, speed_kb)
        except Exception:
            try:
                from config import record_cdn_speed
                record_cdn_speed(host, speed_kb)
            except Exception:
                pass

    def _get_recorded_cdn_speeds(self):
        try:
            from calibre_plugins.libgen_store.config import get_fastest_cdns
            return dict(get_fastest_cdns())
        except Exception:
            try:
                from config import get_fastest_cdns
                return dict(get_fastest_cdns())
            except Exception:
                return {}

    def _source_speed_score(self, source, recorded_speeds=None):
        if recorded_speeds is None:
            recorded_speeds = self._get_recorded_cdn_speeds()
        stream_host = urlparse(source.get("stream_url", "")).netloc.lower()
        learned_speed = float(recorded_speeds.get(stream_host, 0.0) or 0.0)
        probe_speed = float(source.get("probe_speed_kb", 0.0) or 0.0)
        return max(learned_speed, probe_speed)

    def _rank_sources_by_throughput(self, sources):
        recorded_speeds = self._get_recorded_cdn_speeds()
        return sorted(
            sources,
            key=lambda source: self._source_speed_score(source, recorded_speeds),
            reverse=True,
        )

    def get_fallback_detail_urls(self, detail_url):
        """
        Extracts the MD5 and path from a detail URL and constructs equivalent URLs
        across all configured mirrors for robust auto-failover, prioritizing the last successful mirror.
        """

        if not detail_url:
            return []

        urls = []
        parsed = urlparse(detail_url)
        source_host = parsed.netloc.lower()
        md5_match = _RE_MD5.search(detail_url)
        md5 = md5_match.group(1) if md5_match else None

        last_succ = ""
        try:
            from calibre_plugins.libgen_store.config import prefs
            last_succ = prefs.get("last_successful_mirror", "").strip().rstrip("/")
        except Exception:
            pass

        ordered_mirrors = list(self.mirrors)
        if last_succ:
            clean_last = last_succ.rstrip("/")
            ordered_mirrors = [clean_last] + [m for m in ordered_mirrors if m.rstrip("/") != clean_last]

        if md5:
            urls.append(f"https://library.lol/main/{md5}")
            urls.append(f"https://libgen.me/item/detail/{md5}")
            
        for m in ordered_mirrors:
            clean_m = _clean_mirror_url(m)
            if not clean_m:
                continue

            target_host = urlparse(clean_m).netloc.lower()
            is_modern_target = any(
                target_host.endswith(h)
                for h in ("libgen.li", "libgen.me", "libgen.vg", "libgen.gl", "libgen.bz", "libgen.la")
            )
            is_classic_target = any(target_host.endswith(h) for h in ("libgen.is", "libgen.rs", "libgen.st"))
            is_ads_path = parsed.path.startswith(("/ads.php", "/index.php"))
            is_me_detail_path = parsed.path.startswith("/item/detail/")
            is_classic_path = parsed.path.startswith(("/book/index.php", "/book/"))
            can_reuse_path = (
                (is_modern_target and is_ads_path)
                or (target_host.endswith("libgen.me") and is_me_detail_path)
                or (is_classic_target and is_classic_path)
            )
            if parsed.path and can_reuse_path and not parsed.path.startswith("/main/"):
                v1 = f"{clean_m}{parsed.path}"
                if parsed.query:
                    v1 += f"?{parsed.query}"
                if v1 not in urls:
                    urls.append(v1)

            if md5:
                v2 = f"{clean_m}/ads.php?md5={md5}"
                if v2 not in urls:
                    urls.append(v2)
                if clean_m.endswith("libgen.me"):
                    v3 = f"{clean_m}/item/detail/{md5}"
                    if v3 not in urls:
                        urls.append(v3)

        if md5 and f"https://libgen.li/ads.php?md5={md5}" not in urls:
            urls.append(f"https://libgen.li/ads.php?md5={md5}")

        if detail_url not in urls:
            urls.append(detail_url)

        return urls

    def _probe_source(self, url, timeout=10):
        """
        Probes a candidate mirror detail URL, resolves direct link,
        follows redirect to CDN stream URL, checks range support and Content-Length.
        Samples the first 64 KB to validate the stream and estimate CDN throughput.
        Returns dict with mirror info or None.
        """
        try:
            host = urlparse(url).netloc
            download_url, cover_url = self.resolve_details(url, timeout=timeout)
            if not download_url:
                return None

            b = self._get_browser()
            with self._open_url(b, download_url, timeout=timeout) as resp:
                stream_url = resp.geturl()
                headers = resp.info()
    
                try:
                    total_bytes = int(headers.get("Content-Length", 0))
                except (ValueError, TypeError):
                    total_bytes = 0
    
                accepts_ranges = "bytes" in headers.get("Accept-Ranges", "").lower()
    
                sample_start = time.time()
                sample = resp.read(64 * 1024)
                sample_elapsed = max(time.time() - sample_start, 0.001)
                probe_speed_kb = (len(sample) / 1024.0) / sample_elapsed if sample else 0.0

            return {
                "host": host,
                "detail_url": url,
                "direct_url": download_url,
                "stream_url": stream_url,
                "total_bytes": total_bytes,
                "accepts_ranges": accepts_ranges,
                "probe_speed_kb": probe_speed_kb,
                "cover_url": cover_url,
            }
        except Exception:
            return None

    def _download_segment(
        self,
        candidate_stream_urls,
        start_byte,
        end_byte,
        part_path,
        progress_chunk_cb=None,
        abort_check=None,
    ):
        """
        Downloads a byte range [start_byte, end_byte] to part_path with multi-source failover.
        """
        import mechanize
        expected_len = end_byte - start_byte + 1
        last_err = None

        for stream_url in candidate_stream_urls:
            if abort_check and abort_check():
                raise Exception("Stopped by user")

            bytes_written = 0
            chunk_size = 128 * 1024
            start_time = time.time()
            try:
                b = self._get_browser()
                req = mechanize.Request(
                    stream_url,
                    headers={
                        "Range": f"bytes={start_byte}-{end_byte}",
                        "Accept-Encoding": "identity",
                        "User-Agent": self.USER_AGENT,
                    },
                )
                with self._open_url(b, req, timeout=self.timeout * 2) as resp:
                    code = getattr(resp, "code", 200)
                    content_range = resp.headers.get("Content-Range", "")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range.strip())
                    if code != 206 or not match or (
                        int(match.group(1)), int(match.group(2))
                    ) != (start_byte, end_byte):
                        raise Exception(f"Invalid range response: HTTP {code}, {content_range!r}")
    
                    with open(part_path, "wb") as f:
                        while True:
                            if abort_check and abort_check():
                                raise Exception("Stopped by user")
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            if bytes_written + len(chunk) > expected_len:
                                raise Exception("Range response exceeded requested size")
                            f.write(chunk)
                            bytes_written += len(chunk)
                            if progress_chunk_cb:
                                progress_chunk_cb(len(chunk))

                if expected_len > 0 and bytes_written != expected_len:
                    raise Exception(
                        f"Incomplete segment: got {bytes_written}/{expected_len} bytes"
                    )

                elapsed = max(time.time() - start_time, 0.001)
                self._record_cdn_speed(stream_url, (bytes_written / 1024.0) / elapsed)
                return part_path
            except Exception as e:
                last_err = e
                if progress_chunk_cb and bytes_written:
                    progress_chunk_cb(-bytes_written)
                if os.path.exists(part_path):
                    try:
                        os.remove(part_path)
                    except Exception:
                        pass
                continue

        raise Exception(f"Segment {start_byte}-{end_byte} failed on all sources: {last_err}")

    def _segmented_download(
        self,
        range_sources,
        destination_path,
        total_bytes,
        cover_url,
        log_callback=None,
        progress_callback=None,
        link_callback=None,
        abort_check=None,
    ):
        """
        Executes parallel segmented download across multiple working mirrors,
        pieces the parts together, and verifies integrity.
        """
        num_segments = min(len(range_sources), 4)
        part_size = total_bytes // num_segments
        ranges = []
        for i in range(num_segments):
            start = i * part_size
            end = total_bytes - 1 if i == num_segments - 1 else (i + 1) * part_size - 1
            ranges.append((start, end))

        ranked_sources = self._rank_sources_by_throughput(range_sources)
        source_hosts = [urlparse(s["stream_url"]).netloc or s["host"] for s in ranked_sources[:num_segments]]
        if log_callback:
            log_callback(
                f"⚡ Piece-together active: {num_segments} parallel segments across {', '.join(source_hosts)}"
            )

        if link_callback:
            link_callback(ranked_sources[0]["stream_url"], "segmented")

        all_stream_urls = [s["stream_url"] for s in ranked_sources]

        progress_lock = threading.Lock()
        shared_bytes = [0]
        start_time = time.time()
        last_cb = [0.0]

        def on_chunk(chunk_len):
            with progress_lock:
                shared_bytes[0] += chunk_len
                current = shared_bytes[0]
                now = time.time()
                
                if progress_callback:
                    if now - last_cb[0] >= 0.1 or current == total_bytes:
                        elapsed = now - start_time
                        speed_kb = (current / 1024) / elapsed if elapsed > 0 else 0
                        progress_callback(current, total_bytes, speed_kb)
                        last_cb[0] = now

        part_paths = [f"{destination_path}.part{i}" for i in range(num_segments)]

        def worker(idx):
            start, end = ranges[idx]
            rotated_urls = all_stream_urls[idx:] + all_stream_urls[:idx]
            part_path = part_paths[idx]
            return self._download_segment(
                rotated_urls,
                start,
                end,
                part_path,
                progress_chunk_cb=on_chunk,
                abort_check=abort_check,
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_segments) as pool:
                futures = [pool.submit(worker, i) for i in range(num_segments)]
                for fut in concurrent.futures.as_completed(futures):
                    if abort_check and abort_check():
                        raise Exception("Stopped by user")
                    fut.result()

            if abort_check and abort_check():
                raise Exception("Stopped by user")

            if log_callback:
                log_callback(f"Piecing together {num_segments} segments into complete file...")

            dest_dir = os.path.dirname(destination_path)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)

            with open(destination_path, "wb") as outfile:
                for part_path in part_paths:
                    with open(part_path, "rb") as infile:
                        shutil.copyfileobj(infile, outfile, length=128 * 1024)
                    try:
                        os.remove(part_path)
                    except Exception:
                        pass

            final_size = os.path.getsize(destination_path)
            if total_bytes > 0 and final_size != total_bytes:
                raise Exception(f"Reassembled file size mismatch: expected {total_bytes}, got {final_size}")

            if log_callback:
                log_callback(f"✓ Reassembled complete file ({final_size:,} bytes) across {num_segments} mirrors.")

            try:
                from calibre_plugins.libgen_store.config import record_successful_mirror
                for s in ranked_sources[:num_segments]:
                    record_successful_mirror(f"https://{s['host']}")
            except Exception:
                pass

            return destination_path, cover_url

        except Exception as e:
            for p in part_paths:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            if os.path.exists(destination_path):
                try:
                    os.remove(destination_path)
                except Exception:
                    pass
            raise e

    def _find_alternative_md5_by_title(self, current_md5, title, author=None, ext=None, log_callback=None):
        """
        Lean secondary fallback: when primary MD5 fails across all mirrors,
        queries 1 reliable mirror by Title to discover alternative working MD5 hashes.
        Uses minimal network resources (1 query).
        """
        if not title or len(title.strip()) < 3:
            return None

        # Clean title: take first segment before punctuation/subtitles
        clean_title = re.split(r'[:(;,]', title)[0].strip()
        if len(clean_title) < 3:
            clean_title = title.strip()[:40]

        if log_callback:
            log_callback(f"🔍 Lean fallback: searching mirror for alternative upload of \"{clean_title[:35]}\"...")

        clean_mirrors = [m.strip().rstrip("/") for m in self.mirrors if m.strip()]
        if not clean_mirrors:
            return None

        target_mirror = clean_mirrors[0]
        try:
            b = self._get_browser()
            query_url = f"{target_mirror}/index.php?req={quote_plus(clean_title)}&columns%5B%5D=t&res=10"
            with self._open_url(b, query_url, timeout=8) as resp:
                html = resp.read()
            soup = BeautifulSoup(html, HTML_PARSER)
            candidate_books = self._parse_search_page(soup, target_mirror)

            target_ext = (ext or "").lower()
            for cand in candidate_books:
                if target_ext and (cand.extension or "").lower() != target_ext:
                    continue
                m = _RE_MD5.search(cand.detail_url)
                cand_md5 = m.group(1).lower() if m else None
                if cand_md5 and cand_md5 != (current_md5 or "").lower():
                    if log_callback:
                        log_callback(f"✓ Found alternative upload (MD5: {cand_md5[:8]}...) via title search.")
                    return cand.detail_url
        except Exception as e:
            if log_callback:
                log_callback(f"Alternative title search skipped ({e}).")
        return None

    def resolve_and_download(
        self,
        detail_url,
        destination_path,
        book_title=None,
        book_author=None,
        book_ext=None,
        log_callback=None,
        progress_callback=None,
        link_callback=None,
        abort_check=None,
        fast_mode=False,
    ):
        """
        Resolves direct download links and streams files.
        Concurrently probes candidate mirrors, downloads via multi-threaded segmented
        piece-together if supported, with automatic failover to single-stream mirror downloads.
        In fast_mode: uses 3s probe timeout and skips directly to failed list without long fallback chains.
        """

        candidate_urls = self.get_fallback_detail_urls(detail_url)
        if not candidate_urls:
            raise Exception("No candidate mirror URLs found")

        probe_timeout = 3.0 if fast_mode else 10.0
        if log_callback:
            mode_tag = " [Fast Mode]" if fast_mode else ""
            log_callback(f"Probing {len(candidate_urls)} candidate mirrors concurrently for MD5 file{mode_tag}...")

        # Step 1: Concurrently probe candidate mirrors
        working_sources = []
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(candidate_urls), 5))
        futures = {}
        try:
            futures = {pool.submit(self._probe_source, u, probe_timeout): u for u in candidate_urls}
            for fut in concurrent.futures.as_completed(futures):
                if abort_check and abort_check():
                    raise Exception("Stopped by user")
                try:
                    res = fut.result()
                    if res:
                        working_sources.append(res)
                        if log_callback:
                            log_callback(f"✓ Mirror {res['host']} online (size: {res['total_bytes']:,} bytes, range: {res['accepts_ranges']})")
                        # Two independent streams are enough to start; slow probes
                        # must not delay the transfer behind their full timeouts.
                        if len({s['stream_url'] for s in working_sources}) >= 2:
                            break
                except Exception:
                    pass
        finally:
            for future in futures:
                future.cancel()
            pool.shutdown(wait=False)

        # Fast Mode check: if no responsive mirrors after fast probe, skip immediately
        if fast_mode and not working_sources:
            raise Exception("Skipped (troubled / unresponsive mirrors in fast mode)")

        # Step 2: Check if multi-mirror segmented piece-together is viable
        range_sources = [
            s for s in working_sources
            if s.get("accepts_ranges") and s.get("total_bytes", 0) > 200 * 1024
        ]

        # Only combine equal-sized objects, and avoid duplicate CDN streams.
        if range_sources:
            expected_size = range_sources[0]["total_bytes"]
            unique_sources = {}
            for source in range_sources:
                if source["total_bytes"] == expected_size:
                    unique_sources.setdefault(source["stream_url"], source)
            range_sources = list(unique_sources.values())

        if len(range_sources) >= 2:
            try:
                total_bytes = range_sources[0]["total_bytes"]
                cover_url = next((s["cover_url"] for s in range_sources if s.get("cover_url")), None)
                return self._segmented_download(
                    range_sources,
                    destination_path,
                    total_bytes,
                    cover_url,
                    log_callback=log_callback,
                    progress_callback=progress_callback,
                    link_callback=link_callback,
                    abort_check=abort_check,
                )
            except Exception as seg_err:
                if abort_check and abort_check():
                    raise Exception("Stopped by user")
                if fast_mode:
                    raise Exception(f"Skipped (fast mode segmented error: {seg_err})")
                if log_callback:
                    log_callback(f"⚠ Segmented download error ({seg_err}). Falling back to single-stream...")

        # Step 3: Fallback - single stream download from first working source or sequential failover
        if working_sources:
            for src in working_sources:
                if abort_check and abort_check():
                    raise Exception("Stopped by user")
                host = src["host"]
                if link_callback:
                    link_callback(src["stream_url"], "streaming")
                if log_callback:
                    log_callback(f"Streaming directly via {host}...")
                try:
                    self.download_file(
                        src["stream_url"],
                        destination_path,
                        progress_callback=progress_callback,
                        abort_check=abort_check,
                    )
                    if log_callback:
                        log_callback(f"✓ Download completed successfully via {host}.")
                    try:
                        from calibre_plugins.libgen_store.config import record_successful_mirror
                        record_successful_mirror(f"https://{host}")
                    except Exception:
                        pass
                    return destination_path, src.get("cover_url")
                except Exception as stream_err:
                    if abort_check and abort_check():
                        raise Exception("Stopped by user")
                    if fast_mode:
                        raise Exception(f"Skipped (fast mode stream error on {host}: {stream_err})")
                    if log_callback:
                        log_callback(f"Stream error on {host}: {stream_err}. Retrying next source...")
                    continue

        # In Fast Mode, skip long sequential fallback chain
        if fast_mode:
            raise Exception("Skipped (fast mode: all online candidate mirrors failed)")

        # Step 4: Lean Secondary Fallback (Non-MD5 Title Search) before exhaustive sequential probe
        if not working_sources and book_title:
            cur_md5_match = _RE_MD5.search(detail_url)
            cur_md5 = cur_md5_match.group(1) if cur_md5_match else None
            alt_url = self._find_alternative_md5_by_title(
                cur_md5, book_title, author=book_author, ext=book_ext, log_callback=log_callback
            )
            if alt_url:
                return self.resolve_and_download(
                    alt_url,
                    destination_path,
                    book_title=None,
                    book_author=None,
                    book_ext=None,
                    log_callback=log_callback,
                    progress_callback=progress_callback,
                    link_callback=link_callback,
                    abort_check=abort_check,
                    fast_mode=fast_mode,
                )

        # Step 5: Sequential fallback across all candidate URLs if probe missed anything
        last_error = None
        for url in candidate_urls:
            if abort_check and abort_check():
                raise Exception("Stopped by user")

            host = urlparse(url).netloc
            if link_callback:
                link_callback(url, "resolving")
            if log_callback:
                log_callback(f"Trying mirror link (sequential fallback): {url}")

            download_url, cover_url = self.resolve_details(url, timeout=10)
            if abort_check and abort_check():
                raise Exception("Stopped by user")

            if not download_url:
                continue

            if link_callback:
                link_callback(download_url, "streaming")

            try:
                self.download_file(
                    download_url,
                    destination_path,
                    progress_callback=progress_callback,
                    abort_check=abort_check,
                )
                if log_callback:
                    log_callback(f"✓ Download completed successfully via {host}.")
                try:
                    from calibre_plugins.libgen_store.config import record_successful_mirror
                    record_successful_mirror(f"https://{host}")
                except Exception:
                    pass
                return destination_path, cover_url
            except Exception as e:
                if abort_check and abort_check():
                    raise Exception("Stopped by user")
                last_error = e
                continue

        raise Exception(f"All mirrors failed: {last_error or 'Could not resolve download links'}")

    def ping_mirror(self, mirror_url, timeout=8):

        """
        Tests a mirror URL and measures both latency and bandwidth by downloading a small payload.
        Returns:
            (is_ok: bool, latency_ms: int, bandwidth_kb_s: float, speed_str: str, status_msg: str)
        """
        import time
        t0 = time.time()
        b = self._get_browser()
        try:
            url = mirror_url.strip().rstrip("/")
            # 1. Initial connection / TTFB latency
            with self._open_url(b, url, timeout=timeout) as resp:
                t_connected = time.time()
                latency = int((t_connected - t0) * 1000)
    
                code = getattr(resp, "code", 200)
                if code and code >= 400:
                    return False, latency, 0.0, "0 KB/s", f"HTTP {code}"
    
                # 2. Download transfer rate (bandwidth test on small payload)
                t_dl_start = time.time()
                data = resp.read()
                dl_time = max(time.time() - t_dl_start, 0.005)
                bytes_read = len(data)

            # If root response was empty or too small, test against a static asset
            if bytes_read < 1024:
                for test_asset in ["/favicon.ico", "/index.php", "/img/blank.png"]:
                    try:
                        asset_url = urljoin(url + "/", test_asset.lstrip("/"))
                        t_sub = time.time()
                        with self._open_url(b, asset_url, timeout=timeout) as sub_resp:
                            sub_data = sub_resp.read()
                            sub_time = max(time.time() - t_sub, 0.005)
                        if len(sub_data) > bytes_read:
                            bytes_read = len(sub_data)
                            dl_time = sub_time
                            break
                    except Exception:
                        continue

            if bytes_read > 0 and dl_time > 0:
                speed_kb_s = (bytes_read / 1024.0) / dl_time
                if speed_kb_s >= 1024.0:
                    speed_str = f"{speed_kb_s / 1024.0:.1f} MB/s"
                else:
                    speed_str = f"{speed_kb_s:.0f} KB/s"
            else:
                speed_kb_s = 0.0
                speed_str = "< 10 KB/s"

            return True, latency, speed_kb_s, speed_str, "Online"
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            err = str(e)
            status_msg = "Timed out" if "timed out" in err.lower() else f"Error: {err[:30]}"
            return False, latency, 0.0, "0 KB/s", status_msg
