#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Offline unit & regression tests for LibGen Downloader plugin.
Verifies parsing fixtures, deduplication, diagnostic collection, and module integrity.
Run via: calibre-debug test_plugin.py
"""

import sys
import os
from bs4 import BeautifulSoup

# Ensure current directory is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper import LibgenScraper, LibgenBook, HTML_PARSER
from log_collector import collect_diagnostics
import config


# ----------------------------------------------------------------------
# HTML Fixtures for LibGen Table Formats
# ----------------------------------------------------------------------

HTML_LIBGEN_PLUS = """
<table id="tablelibgen">
  <tbody>
    <tr>
      <td>Dune</td>
      <td>Frank Herbert</td>
      <td>Chilton</td>
      <td>1965</td>
      <td>English</td>
      <td>412</td>
      <td>2 MB</td>
      <td>EPUB</td>
      <td><a href="/ads.php?md5=a1b2c3d4e5f60718293a4b5c6d7e8f90">Download</a></td>
    </tr>
  </tbody>
</table>
"""

HTML_COMICS_COLSPAN = """
<table id="tablelibgen">
  <tbody>
    <tr>
      <td colspan="5">Watchmen #01 (1986)<nobr> [Series]</nobr></td>
      <td>32</td>
      <td>45 MB</td>
      <td>CBR</td>
      <td><a href="/ads.php?md5=b2c3d4e5f60718293a4b5c6d7e8f90a1">Download</a></td>
    </tr>
  </tbody>
</table>
"""

HTML_CLASSIC_TABLE = """
<table class="c" rules="rows">
  <tr>
    <td>ID</td><td>Author</td><td>Title</td><td>Publisher</td><td>Year</td>
    <td>Pages</td><td>Language</td><td>Size</td><td>Extension</td><td>Mirrors</td>
  </tr>
  <tr>
    <td>1001</td>
    <td>Isaac Asimov</td>
    <td><font color="green">[Foundation 01]</font> Foundation</td>
    <td>Gnome Press</td>
    <td>1951</td>
    <td>255</td>
    <td>English</td>
    <td>1.5 MB</td>
    <td>EPUB</td>
    <td><a href="http://libgen.is/get.php?md5=c3d4e5f60718293a4b5c6d7e8f90a1b2">Mirror 1</a></td>
  </tr>
</table>
"""


def test_imports():
    print("[1/6] Testing module imports and dual-mode compatibility...")
    import ui
    import dialog
    import workers
    import queue_manager
    import review_dialog
    import csv_importer
    import log_collector
    print("  ✓ All 9 core plugin modules imported cleanly.")


def test_parsing_libgen_plus():
    print("[2/6] Testing LibGen Plus (#tablelibgen) HTML parser...")
    scraper = LibgenScraper(mirrors=["https://libgen.li"])
    soup = BeautifulSoup(HTML_LIBGEN_PLUS, HTML_PARSER)
    books = scraper._parse_search_page(soup, "https://libgen.li")
    assert len(books) == 1, f"Expected 1 book, got {len(books)}"
    b = books[0]
    assert b.title == "Dune", f"Unexpected title: {b.title}"
    assert b.author == "Frank Herbert", f"Unexpected author: {b.author}"
    assert b.extension == "EPUB", f"Unexpected extension: {b.extension}"
    assert b.md5 == "a1b2c3d4e5f60718293a4b5c6d7e8f90", f"Unexpected md5: {b.md5}"
    print("  ✓ Standard LibGen Plus row parsed accurately.")


def test_parsing_comics_colspan():
    print("[3/6] Testing Comics collapsed colspan=5 parser...")
    scraper = LibgenScraper(mirrors=["https://libgen.li"])
    soup = BeautifulSoup(HTML_COMICS_COLSPAN, HTML_PARSER)
    books = scraper._parse_search_page(soup, "https://libgen.li")
    assert len(books) == 1, f"Expected 1 book, got {len(books)}"
    b = books[0]
    assert "Watchmen" in b.title, f"Unexpected title: {b.title}"
    assert b.extension == "CBR", f"Unexpected extension: {b.extension}"
    assert b.md5 == "b2c3d4e5f60718293a4b5c6d7e8f90a1", f"Unexpected md5: {b.md5}"
    print("  ✓ Collapsed Comics colspan=5 row parsed without IndexError.")


def test_parsing_classic_table():
    print("[4/6] Testing Classic LibGen (table.c) parser...")
    scraper = LibgenScraper(mirrors=["https://libgen.li"])
    soup = BeautifulSoup(HTML_CLASSIC_TABLE, HTML_PARSER)
    books = scraper._parse_search_page(soup, "https://libgen.li")
    assert len(books) == 1, f"Expected 1 book, got {len(books)}"
    b = books[0]
    assert "Foundation" in b.title, f"Unexpected title: {b.title}"
    assert b.author == "Isaac Asimov", f"Unexpected author: {b.author}"
    assert b.extension == "EPUB", f"Unexpected extension: {b.extension}"
    assert b.md5 == "c3d4e5f60718293a4b5c6d7e8f90a1b2", f"Unexpected md5: {b.md5}"
    print("  ✓ Classic table.c row parsed with series tag preservation.")


def test_deduplication_and_diagnostics():
    print("[5/6] Testing book deduplication & diagnostic collector...")
    scraper = LibgenScraper(mirrors=["https://libgen.li"])

    b1 = LibgenBook()
    b1.md5 = "11111111111111111111111111111111"
    b1.title = "Neuromancer"
    b1.author = "William Gibson"
    b1.extension = "PDF"

    b2 = LibgenBook()
    b2.md5 = "11111111111111111111111111111111"
    b2.title = "Neuromancer"
    b2.author = "William Gibson"
    b2.extension = "EPUB"

    # Deduplication should collapse identical MD5s and keep preferred format (EPUB)
    deduped = scraper._deduplicate_books([b1, b2], preferred_format="EPUB")
    assert len(deduped) == 1, f"Expected 1 deduped book, got {len(deduped)}"
    assert deduped[0].extension == "EPUB", f"Expected preferred format EPUB, got {deduped[0].extension}"
    print("  ✓ MD5 deduplication successfully prioritized preferred format.")

    # Diagnostic collector check
    report = collect_diagnostics(session_log="[TEST] Log collector test")
    assert "LibGen Downloader Diagnostic Report" in report
    assert "OS / Platform" in report
    assert "Calibre Version" in report
    assert "[TEST] Log collector test" in report
    print("  ✓ Diagnostic collector generated complete Markdown report.")

    # Session CDN isolation check
    config.reset_session_cdns()
    assert config.get_session_cdns() == []
    config.record_cdn_speed("download.library.lol", 1500.0)
    session_cdns = config.get_session_cdns()
    assert len(session_cdns) == 1
    assert session_cdns[0][0] == "download.library.lol"
    assert not any("bookracy" in h for h, _ in session_cdns)
    config.record_cdn_speed("api.bookracy.com", 2500.0)
    session_cdns2 = config.get_session_cdns()
    assert session_cdns2[0][0] == "api.bookracy.com"
    config.reset_session_cdns()
    assert config.get_session_cdns() == []
    print("  ✓ Session CDN isolation verified (uncontacted CDNs excluded).")


def test_ui_easter_egg_and_visibility():
    print("[6/6] Testing UI easter egg gating and activity log visibility...")
    from qt.core import QApplication, Qt, QMouseEvent, QPointF, QEvent
    app = QApplication.instance() or QApplication([])
    config.prefs["show_download_stats"] = False
    import dialog
    dlg = dialog.LibgenDialog(gui=None)
    assert dlg.show_stats is False
    assert dlg.live_activity_container.isHidden() is True, "Live activity container must be hidden by default"

    # Simulate 3 clicks on version badge to activate easter egg
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    dlg.version_click_count = 2
    dlg.on_version_badge_clicked(ev)
    assert dlg.show_stats is True
    assert dlg.live_activity_container.isHidden() is False, "Live activity container must be visible after 3 clicks"

    # Simulate 3 clicks again to hide
    dlg.version_click_count = 2
    dlg.on_version_badge_clicked(ev)
    assert dlg.show_stats is False
    assert dlg.live_activity_container.isHidden() is True, "Live activity container must be hidden again"

    # Verify redundant buttons are hidden
    assert dlg.fetch_mirrors_btn.isHidden() is True, "fetch_mirrors_btn should be hidden"
    assert dlg.clear_queue_btn.isHidden() is True, "clear_queue_btn should be hidden"
    assert dlg.retry_bookracy_btn.isHidden() is True, "retry_bookracy_btn should be hidden"
    assert dlg.pause_download_btn.isHidden() is True, "pause_download_btn should be hidden"
    assert dlg.sort_speed_btn.isHidden() is True, "sort_speed_btn should be hidden"
    print("  ✓ Redundant GUI buttons verified hidden.")
    print("  ✓ Easter egg toggle and live activity log visibility verified.")


def main():
    print("====================================================================")
    print("  LibGen Downloader Offline Unit & Regression Test Suite")
    print("====================================================================\n")
    try:
        test_imports()
        test_parsing_libgen_plus()
        test_parsing_comics_colspan()
        test_parsing_classic_table()
        test_deduplication_and_diagnostics()
        test_ui_easter_egg_and_visibility()
        print("\n====================================================================")
        print("  ✓ ALL OFFLINE TESTS PASSED CLEANLY (6/6)")
        print("====================================================================")
        return 0
    except AssertionError as e:
        import traceback
        traceback.print_exc()
        print(f"\n✗ ASSERTION FAILED: {e}")
        return 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
