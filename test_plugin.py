#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for the LibGen Calibre Store plugin.
Run via: calibre-debug test_plugin.py
"""

import sys
import importlib


def main():
    print("Initializing Calibre plugin system...")
    from calibre.customize.ui import initialize_plugins
    initialize_plugins()

    print("Testing LibGen plugin import...")
    try:
        m = importlib.import_module("calibre_plugins.libgen_store.store")
        cfg = importlib.import_module("calibre_plugins.libgen_store.config")
        print("✓ Modules imported successfully.")
    except Exception as e:
        print(f"✗ Failed to import plugin module: {e}")
        return 1

    print(f"Current preferences: Language={cfg.prefs.get('preferred_language')}, Format={cfg.prefs.get('preferred_format')}, FilterMode={cfg.prefs.get('filter_mode')}")

    print("\nExecuting search for 'Dune Frank Herbert' (max_results=3)...")
    store = m.LibgenStore(None, "LibGen")
    results = list(store.search("Dune Frank Herbert", max_results=3, timeout=30))
    print(f"✓ Search returned {len(results)} items:")

    for i, r in enumerate(results[:2], 1):
        print(f"\n[{i}] {r.title[:45]}")
        print(f"    Author:   {r.author[:30]}")
        print(f"    Format:   {r.formats}")
        print(f"    Price:    {r.price}")
        print(f"    Detail:   {r.detail_item}")

        # Test resolving download and cover details
        print("    Fetching download details...")
        modified = store.get_details(r, timeout=15)
        dl = r.downloads.get(r.formats, "None")
        print(f"    Modified: {modified}")
        print(f"    Download: {dl[:60]}...")
        print(f"    Cover:    {r.cover_url or 'None'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
