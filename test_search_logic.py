"""Offline search logic regression tests; no Calibre installation required."""
import io
import sys
import types
import unittest
from contextlib import contextmanager
from unittest.mock import patch

with patch.dict(sys.modules, {"calibre": types.SimpleNamespace(browser=None)}):
    from scraper import LibgenBook, LibgenScraper


class Response(io.BytesIO):
    def close(self):
        pass


def book(title, detail_url):
    item = LibgenBook()
    item.title = title
    item.author = "Author"
    item.language = "English"
    item.extension = "EPUB"
    item.detail_url = detail_url
    return item


class SearchLogicTests(unittest.TestCase):
    def make_scraper(self, mirrors):
        scraper = LibgenScraper.__new__(LibgenScraper)
        scraper.mirrors = mirrors
        scraper.timeout = 1
        scraper._mirror_cooldowns = {}
        scraper._get_browser = lambda: object()
        return scraper

    def test_duplicate_mirrors_are_submitted_once(self):
        scraper = self.make_scraper(["https://libgen.li", "https://libgen.li"])
        opened_urls = []

        @contextmanager
        def open_url(_browser, url, timeout=None):
            opened_urls.append(url)
            yield Response(b"<html></html>")

        scraper._open_url = open_url
        scraper._parse_search_page = lambda _soup, mirror: [
            book("Foundation", mirror + "/ads.php?md5=0123456789abcdef0123456789abcdef")
        ]

        results = scraper.search("Foundation", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(opened_urls), 1)

    def test_final_result_reuses_existing_ranked_books(self):
        scraper = self.make_scraper(["https://libgen.li"])

        @contextmanager
        def open_url(_browser, _url, timeout=None):
            yield Response(b"<html></html>")

        rank_calls = []
        scraper._open_url = open_url
        scraper._parse_search_page = lambda _soup, mirror: [
            book("Foundation", mirror + "/ads.php?md5=0123456789abcdef0123456789abcdef")
        ]

        original_rank = scraper._filter_and_rank

        def counting_rank(*args, **kwargs):
            rank_calls.append(1)
            return original_rank(*args, **kwargs)

        scraper._filter_and_rank = counting_rank

        results = scraper.search("Foundation", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(rank_calls), 1)


if __name__ == "__main__":
    unittest.main()
