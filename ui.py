#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Calibre InterfaceAction plugin implementation for LibGen Downloader.
Adds a dedicated button to Calibre's main toolbar and menu.
"""

from qt.core import QIcon, QPixmap
from calibre.gui2.actions import InterfaceAction
from calibre_plugins.libgen_store.dialog import LibgenDialog


class LibgenAction(InterfaceAction):
    name = "LibGen Downloader"
    action_spec = ("LibGen Downloader", None, "Search and bulk download books from LibGen", "Ctrl+Shift+L")
    action_type = "current"

    def genesis(self):
        self.qaction.setText("LibGen")
        self.qaction.setToolTip("Search, bulk queue, and download books from LibGen directly into Calibre")

        # Load plugin toolbar icon from zipped resources
        try:
            res = self.load_resources(["images/icon.png"])
            if "images/icon.png" in res:
                pixmap = QPixmap()
                pixmap.loadFromData(res["images/icon.png"])
                self.qaction.setIcon(QIcon(pixmap))
        except Exception:
            pass

        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        d = LibgenDialog(self.gui)
        d.exec()
