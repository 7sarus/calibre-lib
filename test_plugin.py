#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for the LibGen Downloader Calibre InterfaceAction plugin.
Run via: calibre-debug test_plugin.py
"""

import sys
import importlib


def main():
    print("Initializing Calibre plugin system...")
    from calibre.customize.ui import initialize_plugins
    initialize_plugins()

    print("Testing LibGen plugin modules import...")
    try:
        ui_mod = importlib.import_module("calibre_plugins.libgen_store.ui")
        dialog_mod = importlib.import_module("calibre_plugins.libgen_store.dialog")
        scraper_mod = importlib.import_module("calibre_plugins.libgen_store.scraper")
        cfg_mod = importlib.import_module("calibre_plugins.libgen_store.config")
        print("✓ All plugin modules imported successfully:")
        print(f"    - InterfaceAction: {ui_mod.LibgenAction.name}")
        print(f"    - Dialog: {dialog_mod.LibgenDialog}")
        print(f"    - Scraper: {scraper_mod.LibgenScraper}")
    except Exception as e:
        print(f"✗ Failed to import plugin module: {e}")
        return 1

    print("\nTesting LibGen search with live mirror queries...")
    scraper = scraper_mod.LibgenScraper(timeout=20)
    books = scraper.search("Foundation Asimov", max_results=3, preferred_format="EPUB", filter_mode="Prioritize")
    print(f"✓ Search returned {len(books)} books:")
    for i, b in enumerate(books, 1):
        print(f"  [{i}] {b.title[:40]} | Author: {b.author[:25]} | [{b.extension}] | {b.size}")

    if books:
        top_book = books[0]
        print(f"\nTesting direct download resolution for '{top_book.title[:30]}':")
        dl_url, cover = scraper.resolve_details(top_book.detail_url, timeout=15)
        print(f"    Download URL: {dl_url[:60] if dl_url else 'None'}...")
        print(f"    Cover URL:    {cover or 'None'}")
        assert dl_url is not None, "Failed to resolve download URL"
        print("✓ Detail and download resolution passed!")

    print("\n✓ All tests completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
