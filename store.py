#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Calibre StorePlugin implementation for LibGen.
"""

from qt.core import QUrl
from calibre.gui2 import open_url
from calibre.gui2.store import StorePlugin
from calibre.gui2.store.search_result import SearchResult

from calibre_plugins.libgen_store.config import prefs, ConfigWidget
from calibre_plugins.libgen_store.scraper import LibgenScraper


class LibgenStore(StorePlugin):
    def __init__(self, gui, name, config=None, base_plugin=None):
        super().__init__(gui, name, config=config, base_plugin=base_plugin)
        self.name = name

    def _get_scraper(self):
        primary = prefs.get("primary_mirror", "https://libgen.li").strip()
        fallback_str = prefs.get("fallback_mirrors", "")
        fallbacks = [m.strip() for m in fallback_str.split(",") if m.strip()]
        mirrors = [primary] + [m for m in fallbacks if m != primary]
        timeout = int(prefs.get("timeout", 20))
        return LibgenScraper(mirrors=mirrors, timeout=timeout)

    def search(self, query, max_results=10, timeout=60):
        """
        Calibre searches stores concurrently. This generator yields SearchResult items.
        """
        scraper = self._get_scraper()

        preferred_language = prefs.get("preferred_language", "English")
        preferred_format = prefs.get("preferred_format", "Any")
        filter_mode = prefs.get("filter_mode", "Prioritize")

        # Allow user-configured max_results if higher than Calibre's default
        cfg_max = int(prefs.get("max_results", 25))
        fetch_count = max(max_results, cfg_max)

        books = scraper.search(
            query=query,
            max_results=fetch_count,
            preferred_language=preferred_language,
            preferred_format=preferred_format,
            filter_mode=filter_mode,
        )

        for book in books:
            result = SearchResult()
            result.store_name = self.name
            result.title = book.title
            result.author = book.author
            result.price = "Free"
            result.drm = SearchResult.DRM_UNLOCKED
            result.formats = book.extension
            result.detail_item = book.detail_url

            # Provide the mirror URL as initial download if already a direct link
            if book.download_url:
                result.downloads[book.extension] = book.download_url

            if book.cover_url:
                result.cover_url = book.cover_url

            yield result

    def get_details(self, search_result, timeout=60):
        """
        Calibre calls this to fetch detailed metadata and direct download link.
        """
        if not search_result.detail_item:
            return False

        scraper = self._get_scraper()
        download_url, cover_url = scraper.resolve_details(search_result.detail_item, timeout=timeout)

        modified = False
        if download_url:
            search_result.downloads[search_result.formats] = download_url
            modified = True

        if cover_url and not search_result.cover_url:
            search_result.cover_url = cover_url
            modified = True

        return modified

    def open(self, gui=None, parent=None, detail_item=None, external=False):
        """
        Opens the detail link in the default web browser.
        """
        url = detail_item or prefs.get("primary_mirror", "https://libgen.li")
        open_url(QUrl(url))

    def config_widget(self):
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()

