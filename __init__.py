#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Calibre Store Base Plugin wrapper for LibGen.
"""

from calibre.customize import StoreBase


class LibgenStorePlugin(StoreBase):
    name = "LibGen"
    description = (
        "Search and download books directly from Library Genesis mirrors with language "
        "and format filtering/locking into Calibre."
    )
    supported_platforms = ["windows", "osx", "linux"]
    author = "7sarus"
    version = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    # LibGen distributes DRM-free books
    drm_free_only = True
    formats = ["EPUB", "PDF", "MOBI", "AZW3", "DJVU", "CBR", "CBZ"]
    affiliate = False

    actual_plugin = "calibre_plugins.libgen_store.store:LibgenStore"

    def is_customizable(self):
        return True

    def config_widget(self):
        if getattr(self, "actual_plugin_object", None) is not None:
            return self.actual_plugin_object.config_widget()
        from calibre_plugins.libgen_store.config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget):
        if getattr(self, "actual_plugin_object", None) is not None:
            return self.actual_plugin_object.save_settings(config_widget)
        config_widget.save_settings()

