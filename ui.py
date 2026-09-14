#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Calibre InterfaceAction plugin implementation for LibGen Downloader.
Adds a dedicated button to Calibre's main toolbar and menu.
"""

from qt.core import QIcon, QPixmap, QAction
from calibre.gui2.actions import InterfaceAction
from calibre_plugins.libgen_store.dialog import LibgenDialog


class LibgenAction(InterfaceAction):
    name = "LibGen Downloader"
    action_spec = ("LibGen Downloader", None, "Search and bulk download books from LibGen", "Ctrl+Shift+L")
    action_type = "current"

    def genesis(self):
        self.qaction.setText("LibGen")
        self.qaction.setToolTip("Search, queue, and download books from LibGen directly into Calibre")

        # Load plugin toolbar icon from zipped resources
        self.icon = QIcon()
        try:
            res = self.load_resources(["images/icon.png"])
            if "images/icon.png" in res:
                pixmap = QPixmap()
                pixmap.loadFromData(res["images/icon.png"])
                self.icon = QIcon(pixmap)
                self.qaction.setIcon(self.icon)
        except Exception:
            pass

        self.qaction.triggered.connect(self.show_dialog)

    def initialization_complete(self):
        """Add 'Search Author on LibGen' to Calibre's main library list context menu."""
        self.search_author_action = QAction("Search Author on LibGen", self.gui)
        self.search_author_action.setEnabled(True)
        self.search_author_action.setVisible(True)
        if not self.icon.isNull():
            self.search_author_action.setIcon(self.icon)
        self.search_author_action.triggered.connect(self.search_author_from_library)

        if hasattr(self.gui, "library_view"):
            lv = self.gui.library_view
            if hasattr(lv, "context_menu") and lv.context_menu is not None:
                lv.context_menu.aboutToShow.connect(self.update_author_context_menu)
                lv.context_menu.addAction(self.search_author_action)

            # Also attach to split/pin views if present
            if hasattr(lv, "pin_view") and hasattr(lv.pin_view, "context_menu") and lv.pin_view.context_menu is not None:
                lv.pin_view.context_menu.aboutToShow.connect(self.update_author_context_menu)
                lv.pin_view.context_menu.addAction(self.search_author_action)

    def get_selected_author(self):
        """Extracts author name from the currently selected or right-clicked book."""
        try:
            lv = getattr(self.gui, "library_view", None)
            if not lv:
                return None

            # 1. Resolve Book ID: check selection first, then current_id, then index
            selected_ids = lv.get_selected_ids() if hasattr(lv, "get_selected_ids") else []
            book_id = selected_ids[0] if selected_ids else lv.current_id()
            if book_id is None:
                idx = lv.currentIndex()
                if idx.isValid() and hasattr(lv, "model") and lv.model():
                    book_id = lv.model().id(idx.row())

            if book_id is None:
                return None

            db = getattr(self.gui, "current_db", None)
            if not db:
                return None

            # 2. Modern Calibre new_api query (returns tuple like ('Isaac Asimov',))
            if hasattr(db, "new_api"):
                try:
                    authors = db.new_api.field_for("authors", book_id)
                    if authors and len(authors) > 0:
                        clean = authors[0].strip()
                        if clean and clean.lower() != "unknown":
                            return clean
                except Exception:
                    pass

            # 3. Legacy db query fallback
            if hasattr(db, "authors"):
                try:
                    raw = db.authors(book_id)
                    if raw and raw.strip().lower() != "unknown":
                        return raw.split("&")[0].split(";")[0].strip()
                except Exception:
                    pass
        except Exception as e:
            print(f"[LibGen Plugin] Failed to resolve author: {e}")
        return None

    def get_selected_book_info(self):
        """Extracts title, authors, and isbn from the currently selected Calibre book record."""
        try:
            lv = getattr(self.gui, "library_view", None)
            if not lv:
                return None

            selected_ids = lv.get_selected_ids() if hasattr(lv, "get_selected_ids") else []
            book_id = selected_ids[0] if selected_ids else lv.current_id()
            if book_id is None:
                idx = lv.currentIndex()
                if idx.isValid() and hasattr(lv, "model") and lv.model():
                    book_id = lv.model().id(idx.row())

            if book_id is None:
                return None

            db = getattr(self.gui, "current_db", None)
            if not db:
                return None

            title = ""
            author_str = ""
            isbn = ""

            if hasattr(db, "new_api"):
                try:
                    title = db.new_api.field_for("title", book_id) or ""
                except Exception:
                    pass
                try:
                    authors = db.new_api.field_for("authors", book_id)
                    if authors:
                        author_str = ", ".join(a.strip() for a in authors if a and a.strip().lower() != "unknown")
                except Exception:
                    pass
                try:
                    identifiers = db.new_api.field_for("identifiers", book_id)
                    if isinstance(identifiers, dict):
                        isbn = identifiers.get("isbn") or identifiers.get("isbn13") or identifiers.get("isbn10") or ""
                except Exception:
                    pass
            elif hasattr(db, "title") and hasattr(db, "authors"):
                try:
                    title = db.title(book_id) or ""
                    author_str = db.authors(book_id) or ""
                except Exception:
                    pass

            if title or author_str or isbn:
                return {
                    "book_id": book_id,
                    "title": title.strip(),
                    "author": author_str.strip(),
                    "isbn": isbn.strip(),
                }
        except Exception as e:
            print(f"[LibGen Plugin] Failed to resolve selected book info: {e}")
        return None

    def update_author_context_menu(self):
        """Updates context menu action text and guarantees it remains active."""
        author = self.get_selected_author()
        if author:
            self.search_author_action.setText(f"Search LibGen for Author: {author}")
        else:
            self.search_author_action.setText("Search Author on LibGen")
        # Keep active so user can always click it
        self.search_author_action.setEnabled(True)
        self.search_author_action.setVisible(True)

    def search_author_from_library(self):
        """Opens LibGen Downloader dialog with author filter pre-filled and other fields set to default."""
        author = self.get_selected_author()
        d = LibgenDialog(self.gui)
        if author:
            d.set_search_query(query=author, field="Author", reset_filters_to_default=True)
        else:
            d.set_search_query(query="", field="Author", reset_filters_to_default=True)
        d.exec()

    def location_selected(self, loc):
        if hasattr(self, "search_author_action"):
            self.search_author_action.setEnabled(True)

    def show_dialog(self):
        book_info = self.get_selected_book_info()
        initial_query = ""
        if book_info:
            t = book_info.get("title", "")
            a = book_info.get("author", "")
            if t and a:
                initial_query = f"{t} {a}"
            elif t:
                initial_query = t
            elif a:
                initial_query = a

        d = LibgenDialog(self.gui, initial_query=initial_query)
        d.exec()


