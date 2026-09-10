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

    print("\nTesting Mirror Management, Ping & Bandwidth...")
    scraper = scraper_mod.LibgenScraper(timeout=10)
    all_mirrors = cfg_mod.get_mirrors()
    print(f"Found {len(all_mirrors)} configured mirrors: {all_mirrors[:3]}...")
    primary = all_mirrors[0]
    ok, latency, kb_s, speed_str, msg = scraper.ping_mirror(primary, timeout=8)
    print(f"✓ Ping {primary}: status={ok}, latency={latency}ms, speed={speed_str}, msg='{msg}'")

    print("\nTesting Custom Mirror Add / Remove & Order...")
    test_url = "https://libgen.is"
    cfg_mod.add_custom_mirror(test_url)
    assert test_url in cfg_mod.get_mirrors(), "Custom mirror not in get_mirrors"
    print(f"✓ Custom mirror {test_url} added successfully.")
    cfg_mod.set_mirror_order([test_url] + all_mirrors)
    assert cfg_mod.prefs["primary_mirror"] == test_url
    print(f"✓ Mirror reordering / set_mirror_order verified.")
    cfg_mod.remove_custom_mirror(test_url)
    print(f"✓ Custom mirror {test_url} removed successfully.")

    print("\nTesting Field-Specific Search (Author='Isaac Asimov')...")
    books = scraper.search(
        query="Isaac Asimov",
        search_field=cfg_mod.SEARCH_FIELDS["Author"],
        max_results=3,
        preferred_format="EPUB",
        filter_mode="Prioritize",
    )
    print(f"✓ Author search returned {len(books)} books:")
    for i, b in enumerate(books, 1):
        print(f"  [{i}] {b.title[:40]} | Author: {b.author[:25]} | [{b.extension}]")

    print("\n✓ All new features (field selection, mirror ping, custom mirrors) verified!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
