#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Calibre User Interface Action Base Plugin wrapper for LibGen Downloader.
"""

from calibre.customize import InterfaceActionBase


class LibgenDownloaderPlugin(InterfaceActionBase):
    name = "LibGen Downloader"
    description = (
        "Dedicated UI to search, queue, and bulk-download books directly from Library Genesis "
        "mirrors with language and format locking into Calibre."
    )
    supported_platforms = ["windows", "osx", "linux"]
    author = "7sarus"
    version = (1, 5, 0)
    minimum_calibre_version = (5, 0, 0)

    actual_plugin = "calibre_plugins.libgen_store.ui:LibgenAction"

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.libgen_store.config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.save_settings()
