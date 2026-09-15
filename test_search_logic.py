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

    def test_mirrors_ordered_by_latency(self):
        mock_calibre = types.ModuleType("calibre")
        mock_calibre_utils = types.ModuleType("calibre.utils")
        mock_calibre_config = types.ModuleType("calibre.utils.config")

        class MockJSONConfig(dict):
            def __init__(self, name):
                super().__init__()
                self.defaults = {}
            def get(self, key, default=None):
                return super().get(key, self.defaults.get(key, default))

        mock_calibre_config.JSONConfig = MockJSONConfig
        mock_calibre.browser = None
        mock_qt = types.ModuleType("qt")
        mock_qt_core = types.ModuleType("qt.core")
        for cls in ("QWidget", "QVBoxLayout", "QFormLayout", "QComboBox", "QLineEdit", "QSpinBox", "QLabel", "QGroupBox", "QCheckBox", "QPushButton", "QMessageBox"):
            setattr(mock_qt_core, cls, type(cls, (), {}))

        modules_patch = {
            "calibre": mock_calibre,
            "calibre.utils": mock_calibre_utils,
            "calibre.utils.config": mock_calibre_config,
            "qt": mock_qt,
            "qt.core": mock_qt_core,
        }

        with patch.dict(sys.modules, modules_patch):
            if "config" in sys.modules:
                del sys.modules["config"]
            import config
            config.prefs["primary_mirror"] = "https://libgen.li"
            config.prefs["fallback_mirrors"] = "https://libgen.vg, https://libgen.gl"
            config.prefs["custom_mirrors"] = []
            config.prefs["mirror_latencies"] = {
                "https://libgen.gl": 120,
                "https://libgen.vg": 45,
                "https://libgen.li": 250,
            }
            ordered = config.get_mirrors()
            self.assertEqual(ordered[0], "https://libgen.vg")
            self.assertEqual(ordered[1], "https://libgen.gl")
            self.assertEqual(ordered[2], "https://libgen.li")


if __name__ == "__main__":
    unittest.main()
