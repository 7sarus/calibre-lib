"""Offline transfer regression tests; no Calibre installation required."""
import io
import os
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

with patch.dict(sys.modules, {"calibre": types.SimpleNamespace(browser=None)}):
    from scraper import LibgenScraper


class Response(io.BytesIO):
    def __init__(self, body, code=206, **headers):
        super().__init__(body)
        self.code = code
        self.headers = headers


class DownloadLogicTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "book")
        self.scraper = LibgenScraper.__new__(LibgenScraper)
        self.scraper.timeout = 1
        self.scraper._get_browser = lambda: None

    def test_ignored_range_fails_over_before_reading(self):
        ignored = Response(b"whole file", code=200)
        valid = Response(b"abc", **{"Content-Range": "bytes 2-4/5"})
        with patch.object(self.scraper, "_open_url", side_effect=[ignored, valid]):
            self.scraper._download_segment(["https://a", "https://b"], 2, 4, self.path)
        with open(self.path, "rb") as result:
            self.assertEqual(result.read(), b"abc")

    def test_retry_rolls_back_progress(self):
        short = Response(b"a", **{"Content-Range": "bytes 0-2/3"})
        valid = Response(b"abc", **{"Content-Range": "bytes 0-2/3"})
        progress = []
        with patch.object(self.scraper, "_open_url", side_effect=[short, valid]):
            self.scraper._download_segment(
                ["https://a", "https://b"], 0, 2, self.path, progress.append
            )
        self.assertEqual(progress, [1, -1, 3])

    def test_range_sources_are_ranked_by_learned_and_probe_speed(self):
        self.scraper._get_recorded_cdn_speeds = lambda: {"fast.cdn": 900.0}
        sources = [
            {"stream_url": "https://slow.cdn/file", "probe_speed_kb": 50.0},
            {"stream_url": "https://probe.cdn/file", "probe_speed_kb": 700.0},
            {"stream_url": "https://fast.cdn/file", "probe_speed_kb": 10.0},
        ]

        ranked = self.scraper._rank_sources_by_throughput(sources)

        self.assertEqual([s["stream_url"] for s in ranked], [
            "https://fast.cdn/file",
            "https://probe.cdn/file",
            "https://slow.cdn/file",
        ])

    def test_successful_segment_records_cdn_speed(self):
        valid = Response(b"abc", **{"Content-Range": "bytes 0-2/3"})
        recorded = []
        self.scraper._record_cdn_speed = lambda url, speed: recorded.append((url, speed))

        with patch.object(self.scraper, "_open_url", return_value=valid):
            self.scraper._download_segment(["https://fast.cdn/file"], 0, 2, self.path)

        self.assertEqual(recorded[0][0], "https://fast.cdn/file")
        self.assertGreater(recorded[0][1], 0)

    def test_truncated_stream_is_not_success(self):
        response = Response(b"abc", code=200, **{"Content-Length": "9"})
        with patch.object(self.scraper, "_open_url", return_value=response):
            with self.assertRaisesRegex(Exception, "Incomplete download"):
                self.scraper.download_file("https://a", self.path)

    def test_transfer_starts_before_slow_probe_finishes(self):
        release = threading.Event()
        slow_started = threading.Event()
        slow_finished = threading.Event()

        def probe(url, timeout):
            if url == "slow":
                slow_started.set()
                release.wait(2)
                slow_finished.set()
                return None
            self.assertTrue(slow_started.wait(1))
            return dict(host=url, stream_url=url, total_bytes=3, accepts_ranges=False)

        self.scraper.get_fallback_detail_urls = lambda url: ["slow", "a", "b"]
        self.scraper._probe_source = probe
        def download(*args, **kwargs):
            self.assertFalse(slow_finished.is_set())

        try:
            with patch.object(self.scraper, "download_file", side_effect=download):
                result = self.scraper.resolve_and_download("detail", self.path)
            self.assertEqual(result, (self.path, None))
        finally:
            release.set()
            self.assertTrue(slow_finished.wait(2))


if __name__ == "__main__":
    unittest.main()
