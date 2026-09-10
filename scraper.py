#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Core HTML scraping and mirror management for LibGen.
"""

from urllib.parse import urljoin, quote_plus
from bs4 import BeautifulSoup
from calibre import browser


class LibgenBook:
    def __init__(self):
        self.id = ""
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
        "https://libgen.vg",
        "https://libgen.gl",
        "https://libgen.bz",
        "https://libgen.la",
        "https://libgen.is",
    ]

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
    )

    def __init__(self, mirrors=None, timeout=20):
        self.mirrors = mirrors or self.DEFAULT_MIRRORS
        self.timeout = timeout

    def _get_browser(self):
        b = browser()
        b.addheaders = [("User-Agent", self.USER_AGENT)]
        return b

    def search(
        self,
        query,
        search_field="",
        selected_mirror=None,
        max_results=25,
        preferred_language="Any",
        preferred_format="Any",
        filter_mode="Prioritize",
    ):
        """
        Search LibGen mirrors for books matching the query.
        Supports field targeting and mirror selection with auto-failover.
        """
        b = self._get_browser()
        books = []
        last_error = None

        encoded_query = quote_plus(query.strip())
        field_param = f"&columns%5B%5D={search_field}" if search_field else ""

        # Determine mirror order: selected mirror first (if valid), followed by remaining mirrors
        mirror_order = list(self.mirrors)
        if selected_mirror and selected_mirror != "Auto":
            clean_selected = selected_mirror.strip().rstrip("/")
            mirror_order = [clean_selected] + [m for m in mirror_order if m.rstrip("/") != clean_selected]

        for mirror in mirror_order:
            mirror = mirror.strip().rstrip("/")
            if not mirror:
                continue

            search_url = f"{mirror}/index.php?req={encoded_query}{field_param}&res={max_results * 2}"
            try:
                resp = b.open(search_url, timeout=self.timeout)
                html = resp.read()
                soup = BeautifulSoup(html, "html.parser")
                books = self._parse_search_page(soup, mirror)
                if books:
                    break
            except Exception as e:
                last_error = e
                continue

        if not books and last_error and not books:
            # If all mirrors failed, return empty or raise
            return []

        # Filter and rank books based on language and format preferences
        filtered_books = self._filter_and_rank(
            books,
            preferred_language=preferred_language,
            preferred_format=preferred_format,
            filter_mode=filter_mode,
        )

        return filtered_books[:max_results]

    def _parse_search_page(self, soup, mirror):
        """
        Parses search result tables across LibGen Plus (#tablelibgen) and standard Libgen formats.
        """
        books = []
        table = soup.select_one("#tablelibgen tbody") or soup.select_one("#tablelibgen")
        if table:
            rows = table.find_all("tr")
            for r in rows:
                cells = r.find_all("td")
                if len(cells) < 8:
                    continue

                # Title column may have multiple child nodes / links
                title_node = cells[0]
                # Filter out unwanted sub-tags like NOBR if present
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

                book = LibgenBook()
                book.title = title
                book.author = author
                book.publisher = publisher
                book.year = year
                book.language = language
                book.pages = pages
                book.size = size
                book.extension = extension
                book.detail_url = detail_url
                books.append(book)

        return books

    def _filter_and_rank(self, books, preferred_language, preferred_format, filter_mode):
        """
        Handles language and format locking/filtering:
        - Strict mode: Completely discards non-matching results.
        - Prioritize mode: Surfaces matching results to the top of the list.
        """
        pref_lang = (preferred_language or "").strip().lower()
        pref_fmt = (preferred_format or "").strip().upper()

        if filter_mode == "Strict":
            strict_list = []
            for b in books:
                if pref_lang and pref_lang != "any":
                    if pref_lang not in b.language.lower():
                        continue
                if pref_fmt and pref_fmt != "ANY":
                    if b.extension != pref_fmt:
                        continue
                strict_list.append(b)
            return strict_list

        # Prioritize Mode: score items
        def get_score(book):
            score = 0
            if pref_lang and pref_lang != "any":
                if pref_lang in book.language.lower():
                    score += 10
            if pref_fmt and pref_fmt != "ANY":
                if book.extension == pref_fmt:
                    score += 20
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
        try:
            resp = b.open(detail_url, timeout=t)
            soup = BeautifulSoup(resp.read(), "html.parser")

            # Extract direct get.php link
            get_link = soup.select_one('a[href*="get.php"]')
            if not get_link:
                # Fallback: look for link containing 'GET' text
                for a in soup.find_all("a"):
                    if a.get_text(strip=True).upper() == "GET" and a.get("href"):
                        get_link = a
                        break

            download_url = (
                urljoin(detail_url, get_link["href"]) if get_link and get_link.get("href") else None
            )

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

    def download_file(self, download_url, destination_path, progress_callback=None):
        """
        Streams a remote file to destination_path with chunked writing.
        Calls progress_callback(bytes_read, total_bytes) on each chunk.
        """
        b = self._get_browser()
        resp = b.open(download_url, timeout=self.timeout * 3)

        total_bytes = 0
        try:
            total_bytes = int(resp.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            total_bytes = 0

        bytes_read = 0
        chunk_size = 64 * 1024  # 64 KB

        with open(destination_path, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                bytes_read += len(chunk)
                if progress_callback:
                    progress_callback(bytes_read, total_bytes)

        return destination_path

    def ping_mirror(self, mirror_url, timeout=5):
        """
        Tests a mirror URL and returns (is_ok: bool, latency_ms: int, status_str: str).
        """
        import time
        t0 = time.time()
        b = self._get_browser()
        try:
            url = mirror_url.strip().rstrip("/")
            resp = b.open(url, timeout=timeout)
            code = getattr(resp, "code", 200)
            latency = int((time.time() - t0) * 1000)
            if code and code >= 400:
                return False, latency, f"HTTP {code}"
            return True, latency, f"{latency} ms"
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            err = str(e)
            if "timed out" in err.lower():
                return False, latency, "Timed out"
            return False, latency, f"Error: {err[:35]}"

