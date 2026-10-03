#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Dedicated UI dialog for LibGen Downloader with search, field selection,
mirror selection/health checks, and queue download manager directly inside Calibre.
"""

import os
import re
import time

try:
    from calibre_plugins.libgen_store.queue_manager import QueueManager
except ImportError:
    from queue_manager import QueueManager

import threading
import collections
from collections import OrderedDict
import concurrent.futures
from urllib.parse import urlparse

from qt.core import (
    Qt,
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTabWidget,
    QProgressBar,
    QMessageBox,
    QThread,
    pyqtSignal,
    QWidget,
    QColor,
    QGroupBox,
    QMenu,
    QShortcut,
    QKeySequence,
    QPlainTextEdit,
    QTimer,
    QCheckBox,
    QSpinBox,
    QStandardItem,
    QStandardItemModel,
    QCompleter,
    QFormLayout,
    QByteArray,
    QRadioButton,
    QButtonGroup,
    QFileDialog,
)

PROGRESS_BAR_STYLE = (
    "QProgressBar { border: 1px solid palette(mid); border-radius: 4px; "
    "background: palette(base); text-align: center; font-size: 11px; "
    "font-weight: 600; color: palette(text); } "
    "QProgressBar::chunk { background: palette(highlight); border-radius: 3px; }"
)

PRIMARY_BUTTON_STYLE = "font-weight: 600; padding: 5px 14px;"
DANGER_BUTTON_STYLE = "font-weight: 600; padding: 5px 14px;"
COMPACT_BUTTON_STYLE = "font-weight: 600; padding: 4px 10px;"
FILTER_BUTTON_STYLE = "padding: 3px 10px;"
FILTER_BUTTON_ACTIVE_STYLE = (
    "font-weight: 600; padding: 3px 10px; "
    "background: palette(highlight); color: palette(highlighted-text);"
)
PANEL_STYLE = (
    "background: palette(base); border: 1px solid palette(mid); "
    "border-radius: 5px; color: palette(text);"
)
MONO_PANEL_STYLE = (
    "background: palette(base); color: palette(text); font-family: monospace; "
    "font-size: 11px; padding: 6px; border: 1px solid palette(mid); border-radius: 4px;"
)

class ToastOverlay(QLabel):
    """Lightweight non-blocking floating toast notification."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "background-color: rgba(20, 24, 30, 230); color: #00d4aa; "
            "border: 1px solid #00d4aa; border-radius: 6px; "
            "padding: 8px 16px; font-weight: 600; font-size: 12px;"
        )
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_toast(self, text, duration_ms=2200):
        self.setText(text)
        self.adjustSize()
        if self.parent():
            p_geom = self.parent().rect()
            x = (p_geom.width() - self.width()) // 2
            y = p_geom.height() - self.height() - 48
            self.move(max(10, x), max(10, y))
        self.raise_()
        self.show()
        self._timer.start(duration_ms)


try:
    from calibre_plugins.libgen_store.progress_delegate import ProgressBarDelegate
except ImportError:
    from progress_delegate import ProgressBarDelegate


try:
    from calibre_plugins.libgen_store.config import (
        prefs,
        SUPPORTED_LANGUAGES,
        SUPPORTED_FORMATS,
        FILTER_MODES,
        SEARCH_FIELDS,
        CATEGORIES,
        get_mirrors,
        set_mirror_order,
        record_mirror_latency,
        add_custom_mirror,
        remove_custom_mirror,
        discard_mirrors,
        PLUGIN_VERSION_STR,
        get_fastest_cdns,
        append_search_history,
        get_search_history,
        get_search_history_filepath,
        append_download_history,
        get_download_history,
        clear_download_history,
        clear_all_history,
        cleanup_expired_history,
        get_pending_searches,
        add_pending_search,
        remove_pending_search,
        clear_pending_searches,
        get_active_backend,
        set_active_backend,
        BACKENDS,
    )
    from calibre_plugins.libgen_store.scraper import LibgenScraper, LibgenBook, get_scraper
except (ImportError, ModuleNotFoundError):
    from config import (
        prefs,
        SUPPORTED_LANGUAGES,
        SUPPORTED_FORMATS,
        FILTER_MODES,
        SEARCH_FIELDS,
        CATEGORIES,
        get_mirrors,
        set_mirror_order,
        record_mirror_latency,
        add_custom_mirror,
        remove_custom_mirror,
        discard_mirrors,
        PLUGIN_VERSION_STR,
        get_fastest_cdns,
        append_search_history,
        get_search_history,
        get_search_history_filepath,
        append_download_history,
        get_download_history,
        clear_download_history,
        clear_all_history,
        cleanup_expired_history,
        get_pending_searches,
        add_pending_search,
        remove_pending_search,
        clear_pending_searches,
        get_active_backend,
        set_active_backend,
        BACKENDS,
    )
    from scraper import LibgenScraper, LibgenBook, get_scraper

try:
    from calibre_plugins.libgen_store.hardcover import (
        fetch_user_shelves_and_lists,
        fetch_shelf_books,
    )
except ImportError:
    try:
        from hardcover import fetch_user_shelves_and_lists, fetch_shelf_books
    except ImportError:
        pass


def serialize_book(book):
    return {
        "id": getattr(book, "id", "") or "",
        "md5": getattr(book, "md5", "") or "",
        "title": getattr(book, "title", "") or "",
        "author": getattr(book, "author", "") or "",
        "publisher": getattr(book, "publisher", "") or "",
        "year": getattr(book, "year", "") or "",
        "language": getattr(book, "language", "") or "",
        "pages": getattr(book, "pages", "") or "",
        "size": getattr(book, "size", "") or "",
        "extension": getattr(book, "extension", "") or "",
        "detail_url": getattr(book, "detail_url", "") or "",
        "download_url": getattr(book, "download_url", "") or "",
        "cover_url": getattr(book, "cover_url", "") or "",
    }


def deserialize_book(d):
    b = LibgenBook()
    for k, v in d.items():
        setattr(b, k, v)
    return b


def sanitize_filename(name):
    """Clean filename of illegal filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:100]

class SizeTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        def _parse(s):
            if not s or s == "-": return 0.0
            s_upper = s.upper()
            try:
                val = float(''.join(c for c in s_upper if c.isdigit() or c == '.'))
                if "KB" in s_upper: return val * 1024
                if "MB" in s_upper: return val * 1024 * 1024
                if "GB" in s_upper: return val * 1024 * 1024 * 1024
                return val
            except:
                return 0.0
        return _parse(self.text()) < _parse(other.text())


class CheckableComboBox(QComboBox):
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(QStandardItemModel(self))
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view().pressed.connect(self.handle_item_pressed)

    def handle_item_pressed(self, index):
        item = self.model().itemFromIndex(index)
        if not item:
            return
        if item.text() == "Any":
            for r in range(self.model().rowCount()):
                it = self.model().item(r)
                if it:
                    it.setCheckState(Qt.CheckState.Checked if r == index.row() else Qt.CheckState.Unchecked)
        else:
            any_item = self.model().item(0)
            if any_item and any_item.text() == "Any":
                any_item.setCheckState(Qt.CheckState.Unchecked)
            new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(new_state)

            has_checked = any(
                self.model().item(r).checkState() == Qt.CheckState.Checked
                for r in range(self.model().rowCount())
                if self.model().item(r)
            )
            if not has_checked and any_item:
                any_item.setCheckState(Qt.CheckState.Checked)

        self.update_display_text()
        self.selection_changed.emit(self.checked_items())

    def add_checkable_items(self, items, checked_items=None):
        self.model().clear()
        checked_set = set(checked_items or ["Any"])
        if not checked_set or "Any" in checked_set:
            checked_set = {"Any"}
        for text in items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            is_chk = (text in checked_set)
            item.setCheckState(Qt.CheckState.Checked if is_chk else Qt.CheckState.Unchecked)
            self.model().appendRow(item)
        self.update_display_text()

    def checked_items(self):
        checked = []
        for r in range(self.model().rowCount()):
            it = self.model().item(r)
            if it and it.checkState() == Qt.CheckState.Checked:
                checked.append(it.text())
        if not checked:
            checked = ["Any"]
        return checked

    LANG_CODE_MAP = {
        "English": "EN",
        "Spanish": "ES",
        "French": "FR",
        "German": "DE",
        "Russian": "RU",
        "Italian": "IT",
        "Portuguese": "PT",
        "Chinese": "ZH",
        "Japanese": "JA",
        "Any": "Any",
    }

    def update_display_text(self):
        items = self.checked_items()
        if "Any" in items or not items:
            self.setEditText("Any")
            self.setToolTip("Filter by languages (Click to check multiple)")
        elif len(items) == 1:
            code = self.LANG_CODE_MAP.get(items[0], items[0][:3].upper())
            self.setEditText(code)
            self.setToolTip(f"Language: {items[0]}")
        else:
            short_codes = [self.LANG_CODE_MAP.get(i, i[:3].upper()) for i in items]
            self.setEditText(", ".join(short_codes))
            self.setToolTip(f"Languages: {', '.join(items)}")

    def hidePopup(self):
        super().hidePopup()
        self.update_display_text()



try:
    from calibre_plugins.libgen_store.workers import SearchWorker, SearchQueueWorker, MirrorHealthWorker, CoverFetchWorker, LiveMirrorWorker, BulkDownloadWorker
except ImportError:
    from workers import SearchWorker, SearchQueueWorker, MirrorHealthWorker, CoverFetchWorker, LiveMirrorWorker, BulkDownloadWorker


class HistorySettingsDialog(QDialog):
    """Configuration dialog for search & download history limits and auto-retention."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("History & Retention Settings")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.save_history_checkbox = QCheckBox("Save search query history and enable autocomplete", self)
        self.save_history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
        form.addRow("Search History:", self.save_history_checkbox)

        self.max_search_spin = QSpinBox(self)
        self.max_search_spin.setRange(5, 1000)
        self.max_search_spin.setValue(int(prefs.get("max_search_history", 50)))
        form.addRow("Max Search Queries:", self.max_search_spin)

        self.max_dl_spin = QSpinBox(self)
        self.max_dl_spin.setRange(5, 1000)
        self.max_dl_spin.setValue(int(prefs.get("max_download_history", 50)))
        form.addRow("Max Download History:", self.max_dl_spin)

        self.retention_spin = QSpinBox(self)
        self.retention_spin.setRange(0, 365)
        self.retention_spin.setSuffix(" days")
        self.retention_spin.setSpecialValueText("Never (Keep indefinitely)")
        self.retention_spin.setValue(int(prefs.get("history_retention_days", 30)))
        self.retention_spin.setToolTip("Auto-clears search queries and download logs older than X days. Set to 0 to disable.")
        form.addRow("Clear History After:", self.retention_spin)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.clear_all_btn = QPushButton("Clear All History", self)
        self.clear_all_btn.clicked.connect(self.on_clear_all)
        btn_row.addWidget(self.clear_all_btn)
        btn_row.addStretch()

        self.save_btn = QPushButton("Save", self)
        self.save_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.save_btn.clicked.connect(self.on_save)
        btn_row.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

    def on_clear_all(self):
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all search query and download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            clear_all_history("all")
            QMessageBox.information(self, "History Cleared", "Search and download history have been cleared.")

    def on_save(self):
        prefs["save_search_history"] = self.save_history_checkbox.isChecked()
        prefs["max_search_history"] = self.max_search_spin.value()
        prefs["max_download_history"] = self.max_dl_spin.value()
        prefs["history_retention_days"] = self.retention_spin.value()
        cleanup_expired_history()
        self.accept()


class CsvImportDialog(QDialog):
    """Dialog to import book lists from CSV/TXT files (Goodreads, StoryGraph, Hardcover, custom) and queue ISBNs/Titles for download."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_dialog = parent
        self.setWindowTitle("Import Books from CSV / TXT File")
        saved_w = min(880, max(480, int(prefs.get("csv_import_dialog_width", 640))))
        saved_h = min(680, max(380, int(prefs.get("csv_import_dialog_height", 460))))
        self.resize(saved_w, saved_h)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(6)

        self.fetched_books = []

        # Top Section: File Selection
        file_group = QGroupBox("Select CSV or TXT File")
        file_layout = QHBoxLayout(file_group)

        self.file_path_edit = QLineEdit(self)
        self.file_path_edit.setPlaceholderText("Select CSV file (Goodreads, StoryGraph, Hardcover export, or custom list)...")
        file_layout.addWidget(self.file_path_edit, stretch=3)

        self.browse_btn = QPushButton("Browse...", self)
        self.browse_btn.clicked.connect(self.browse_csv_file)
        file_layout.addWidget(self.browse_btn)

        self.layout.addWidget(file_group)

        # Options Group
        match_group = QGroupBox("Import Options")
        match_layout = QHBoxLayout(match_group)

        self.skip_library_checkbox = QCheckBox("Skip in-library books", self)
        self.skip_library_checkbox.setToolTip("Checks your Calibre database for matching ISBN or title to avoid duplicate downloads")
        self.skip_library_checkbox.setChecked(bool(prefs.get("csv_skip_in_library", True)))
        self.skip_library_checkbox.stateChanged.connect(lambda v: prefs.__setitem__("csv_skip_in_library", bool(v)))
        match_layout.addWidget(self.skip_library_checkbox)

        self.status_filter_label = QLabel("Filter Status:", self)
        self.status_filter_label.setVisible(False)
        match_layout.addWidget(self.status_filter_label)

        self.status_filter_combo = QComboBox(self)
        self.status_filter_combo.addItem("All Statuses")
        self.status_filter_combo.setVisible(False)
        self.status_filter_combo.currentIndexChanged.connect(lambda _: self.apply_status_filter())
        match_layout.addWidget(self.status_filter_combo)

        match_layout.addStretch(1)

        self.layout.addWidget(match_group)

        # Parsed Books Table
        self.books_table = QTableWidget(self)
        self.books_table.setColumnCount(5)
        self.books_table.setHorizontalHeaderLabels([
            "Title", "Author", "ISBN", "Year", "Status"
        ])
        self.books_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.books_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.books_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.layout.addWidget(self.books_table)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All", self)
        self.select_all_btn.clicked.connect(self.select_all_books)
        btn_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All", self)
        self.deselect_all_btn.clicked.connect(self.deselect_all_books)
        btn_row.addWidget(self.deselect_all_btn)

        btn_row.addStretch()

        self.queue_btn = QPushButton("▶ Add to Queue", self)
        self.queue_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.queue_btn.setToolTip("Add selected books from CSV to the main window's Search Queue")
        self.queue_btn.clicked.connect(self.on_queue_selected)
        btn_row.addWidget(self.queue_btn)

        self.close_btn = QPushButton("Close", self)
        self.close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.close_btn)

        self.layout.addLayout(btn_row)

        self.restore_state()

    def browse_csv_file(self):
        from qt.core import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV or Text File",
            os.path.expanduser("~"),
            "CSV / Text Files (*.csv *.txt *.tsv);;All Files (*)",
        )
        if path:
            self.file_path_edit.setText(path)
            self.parse_csv_file(path)

    def parse_csv_file(self, file_path):
        import csv
        if not os.path.exists(file_path):
            return

        books = []
        statuses = set()
        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                content = f.read()
                f.seek(0)

                # Support plain text files containing one ISBN or Title per line
                if not any(sep in content[:500] for sep in [",", "\t", ";"]):
                    for line in content.splitlines():
                        clean = line.strip()
                        if clean and len(clean) >= 3:
                            isbn_match = re.search(r"\b(97[89]\d{10}|\d{9}[\dX])\b", clean)
                            isbn = isbn_match.group(1) if isbn_match else ""
                            books.append({
                                "title": clean if not isbn else "",
                                "author": "",
                                "best_isbn": isbn,
                                "isbn_13": isbn if len(isbn) == 13 else "",
                                "isbn_10": isbn if len(isbn) == 10 else "",
                                "release_year": "",
                                "csv_status": "",
                            })
                else:
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(content[:2048]) if content.strip() else csv.excel
                    reader = csv.reader(content.splitlines(), dialect=dialect)
                    rows = list(reader)

                    if not rows:
                        return

                    header = [str(c).strip().lower() for c in rows[0]]
                    has_header = any(h in ["title", "author", "isbn", "isbn13", "isbn10", "book id", "year", "status", "exclusive shelf", "shelf", "read status"] for h in header)

                    title_col = -1
                    author_col = -1
                    isbn_col = -1
                    year_col = -1
                    status_col = -1

                    if has_header:
                        for idx, h in enumerate(header):
                            if title_col < 0 and "title" in h:
                                title_col = idx
                            elif author_col < 0 and ("author" in h or "creator" in h):
                                author_col = idx
                            elif isbn_col < 0 and ("isbn" in h or "identifier" in h):
                                isbn_col = idx
                            elif year_col < 0 and ("year" in h or "date" in h or "published" in h):
                                year_col = idx
                            elif status_col < 0 and ("status" in h or "shelf" in h or "state" in h):
                                status_col = idx
                        data_rows = rows[1:]
                    else:
                        data_rows = rows

                    for r in data_rows:
                        if not r:
                            continue
                        row_str = " ".join(r)
                        isbn_match = re.search(r"\b(97[89]\d{10}|\d{9}[\dX])\b", row_str)
                        isbn = isbn_match.group(1) if isbn_match else ""

                        title = r[title_col].strip() if 0 <= title_col < len(r) else ""
                        author = r[author_col].strip() if 0 <= author_col < len(r) else ""
                        year = r[year_col].strip() if 0 <= year_col < len(r) else ""
                        csv_status = r[status_col].strip() if 0 <= status_col < len(r) else ""

                        if csv_status:
                            statuses.add(csv_status)

                        # If no header matched title/author columns, use first non-ISBN fields
                        if not title and not author and not isbn:
                            non_empty = [cell.strip() for cell in r if cell.strip()]
                            if non_empty:
                                title = non_empty[0]
                                if len(non_empty) > 1:
                                    author = non_empty[1]

                        if title or author or isbn:
                            books.append({
                                "title": title,
                                "author": author,
                                "best_isbn": isbn,
                                "isbn_13": isbn if len(isbn) == 13 else "",
                                "isbn_10": isbn if len(isbn) == 10 else "",
                                "release_year": year,
                                "csv_status": csv_status,
                            })

            self.fetched_books = books
            self.setup_status_filter(statuses)
            self.populate_books_table()
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse CSV file:\n{e}")

    def setup_status_filter(self, statuses):
        self.status_filter_combo.blockSignals(True)
        self.status_filter_combo.clear()
        self.status_filter_combo.addItem("All Statuses")
        if statuses:
            for s in sorted(statuses):
                self.status_filter_combo.addItem(s)
            self.status_filter_label.setVisible(True)
            self.status_filter_combo.setVisible(True)
        else:
            self.status_filter_label.setVisible(False)
            self.status_filter_combo.setVisible(False)
        self.status_filter_combo.blockSignals(False)

    def apply_status_filter(self):
        selected_status = self.status_filter_combo.currentText()
        for row in range(self.books_table.rowCount()):
            if row < len(self.fetched_books):
                b = self.fetched_books[row]
                b_status = b.get("csv_status", "")
                if selected_status == "All Statuses" or b_status == selected_status:
                    self.books_table.setRowHidden(row, False)
                else:
                    self.books_table.setRowHidden(row, True)

    def populate_books_table(self):
        self.books_table.setRowCount(len(self.fetched_books))
        for row, b in enumerate(self.fetched_books):
            self.books_table.setItem(row, 0, QTableWidgetItem(b.get("title", "")))
            self.books_table.setItem(row, 1, QTableWidgetItem(b.get("author", "")))
            isbn = b.get("best_isbn") or b.get("isbn_13") or b.get("isbn_10") or ""
            isbn_item = QTableWidgetItem(isbn if isbn else "—")
            self.books_table.setItem(row, 2, isbn_item)
            self.books_table.setItem(row, 3, QTableWidgetItem(str(b.get("release_year") or "")))
            self.books_table.setItem(row, 4, QTableWidgetItem("Ready"))
        self.books_table.selectAll()

    def select_all_books(self):
        self.books_table.selectAll()

    def deselect_all_books(self):
        self.books_table.clearSelection()

    def _is_in_library(self, isbn="", title="", author=""):
        try:
            gui = getattr(self.parent_dialog, "gui", None)
            if not gui or not getattr(gui, "current_db", None):
                return False
            db = gui.current_db
            new_api = getattr(db, "new_api", None)
            if not new_api:
                return False

            if isbn:
                clean_isbn = isbn.replace("-", "").strip()
                if clean_isbn and new_api.search(f"isbn:{clean_isbn}"):
                    return True

            if title:
                # Clean title & subtitles (remove quotes, brackets, subtitles after :)
                clean_t = re.split(r'[:(;,]', title)[0].replace('"', '').strip()
                clean_a = re.split(r'[,;&]', author)[0].replace('"', '').strip() if author else ""
                
                if clean_t:
                    if clean_a and new_api.search(f'title:"={clean_t}" and authors:"={clean_a}"'):
                        return True
                    if new_api.search(f'title:"={clean_t}"'):
                        return True
                    # Partial match if title is long enough
                    if len(clean_t) >= 4 and new_api.search(f'title:"{clean_t}"'):
                        return True
        except Exception:
            pass
        return False

    def on_queue_selected(self):
        all_selected = sorted(set(idx.row() for idx in self.books_table.selectedIndexes()))
        selected_rows = [r for r in all_selected if not self.books_table.isRowHidden(r)]
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select at least one visible book from the table.")
            return

        skip_library = self.skip_library_checkbox.isChecked()
        in_lib_matches = []

        for r in selected_rows:
            if r < len(self.fetched_books):
                b = self.fetched_books[r]
                isbn = b.get("best_isbn") or b.get("isbn_13") or b.get("isbn_10") or ""
                title = b.get("title", "")
                author = b.get("author", "")
                if self._is_in_library(isbn, title, author):
                    in_lib_matches.append((r, b))

        if in_lib_matches:
            reply = QMessageBox.question(
                self,
                "Books Already in Library",
                f"Found {len(in_lib_matches)} book(s) among your selection that are already in your Calibre library.\n\n"
                "Would you like to SKIP these books and queue only new items?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            skip_library = (reply == QMessageBox.StandardButton.Yes)

        added_books = []
        skipped_in_lib = 0

        for r in selected_rows:
            if r >= len(self.fetched_books):
                continue
            b = self.fetched_books[r]
            title = b.get("title", "")
            author = b.get("author", "")
            isbn = b.get("best_isbn") or b.get("isbn_13") or b.get("isbn_10") or ""

            if skip_library and self._is_in_library(isbn, title, author):
                skipped_in_lib += 1
                self.books_table.setItem(r, 4, QTableWidgetItem("Skipped (In Library)"))
                continue

            rec = {
                "title": title,
                "author": author,
                "isbn": isbn,
                "year": b.get("release_year") or "",
            }
            added_books.append(rec)
            self.books_table.setItem(r, 4, QTableWidgetItem("✓ In Search Queue"))

        if not added_books:
            QMessageBox.information(self, "No Books Queued", "No new books were added to Search Queue (all selected books already exist in Calibre library).")
            return

        if self.parent_dialog:
            if not hasattr(self.parent_dialog, "selected_books") or self.parent_dialog.selected_books is None:
                self.parent_dialog.selected_books = []

            existing_sigs = {
                (b.get("isbn", "").strip(), b.get("title", "").strip().lower())
                for b in self.parent_dialog.selected_books
            }
            new_count = 0
            for rec in added_books:
                sig = (rec.get("isbn", "").strip(), rec.get("title", "").strip().lower())
                if sig not in existing_sigs:
                    self.parent_dialog.selected_books.append(rec)
                    existing_sigs.add(sig)
                    new_count += 1

            if hasattr(self.parent_dialog, "update_search_queue_bar"):
                self.parent_dialog.update_search_queue_bar()

            self.parent_dialog.status_label.setText(
                f"Loaded {len(self.parent_dialog.selected_books)} record(s) into Search Queue ({new_count} new from CSV)."
            )

        summary_msg = f"✓ Added {len(added_books)} book(s) to the Search Queue."
        if skipped_in_lib:
            summary_msg += f"\n• Skipped {skipped_in_lib} book(s) already in Calibre library."

        QMessageBox.information(self, "CSV Search Queue", summary_msg)
        self.accept()

    def restore_state(self):
        state_hex = prefs.get("csv_import_table_header", "")
        if state_hex:
            try:
                self.books_table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode("ascii")))
            except Exception:
                pass

    def save_state(self):
        prefs["hardcover_dialog_width"] = self.width()
        prefs["hardcover_dialog_height"] = self.height()
        try:
            prefs["hardcover_books_table_header"] = bytes(
                self.books_table.horizontalHeader().saveState().toHex()
            ).decode("ascii")
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_state()
        super().closeEvent(event)

    def accept(self):
        self.save_state()
        super().accept()

    def reject(self):
        self.save_state()
        super().reject()


class ReviewImportDialog(QDialog):
    """Review modal presented after download completion or abortion to select books for Calibre import."""

    def __init__(self, downloaded_items, is_aborted=False, stats_summary=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Downloaded Books for Import")
        saved_w = min(1200, max(560, int(prefs.get("review_dialog_width", 760))))
        saved_h = min(900, max(360, int(prefs.get("review_dialog_height", 420))))
        self.resize(saved_w, saved_h)
        self.downloaded_items = downloaded_items
        self.is_aborted = is_aborted
        self.stats_summary = stats_summary or {}
        self.approved_items = []

        layout = QVBoxLayout(self)

        status_prefix = "<b>Download stopped early.</b> " if is_aborted else "<b>Bulk download finished.</b> "
        info_text = (
            f"{status_prefix}{len(downloaded_items)} book(s) were successfully downloaded.<br>"
            "Review and choose which books to import into your Calibre library:"
        )
        if self.stats_summary:
            s = self.stats_summary
            cdn_str = ""
            if s.get("fastest_cdns"):
                top_cdn, top_speed = s["fastest_cdns"][0]
                cdn_str = f" &nbsp;|&nbsp; 🚀 CDN: <b>{top_cdn}</b> ({top_speed:.1f} KB/s)"
            info_text += (
                f"<br><span style='font-size: 12px; font-weight: normal;'>"
                f"⏱ Time: <b>{s.get('time_str', '-')}</b> &nbsp;|&nbsp; "
                f"📦 Data: <b>{s.get('size_str', '-')}</b> &nbsp;|&nbsp; "
                f"⚡ Avg Speed: <b>{s.get('speed_str', '-')}</b>{cdn_str}</span>"
            )
        banner = QLabel(info_text, self)
        banner.setWordWrap(True)
        banner.setStyleSheet("padding: 10px 14px; background: palette(alternate-base); color: palette(text); border-radius: 4px; font-size: 13px;")
        layout.addWidget(banner)

        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Import?", "Title", "Author", "Format", "Size"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.table.setRowCount(len(downloaded_items))
        for row, item in enumerate(downloaded_items):
            book = item["book"]
            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, cb_item)
            self.table.setItem(row, 1, QTableWidgetItem(book.title or "Unknown"))
            self.table.setItem(row, 2, QTableWidgetItem(book.author or "Unknown"))
            self.table.setItem(row, 3, QTableWidgetItem(book.extension or "EPUB"))
            self.table.setItem(row, 4, QTableWidgetItem(book.size or "-"))

        state_hex = prefs.get("review_table_header", "")
        if state_hex:
            try:
                self.table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode("ascii")))
            except Exception:
                pass

        layout.addWidget(self.table)

        sel_bar = QHBoxLayout()
        sel_all_btn = QPushButton("Select All", self)
        sel_all_btn.clicked.connect(self.select_all)
        sel_bar.addWidget(sel_all_btn)

        desel_all_btn = QPushButton("Deselect All", self)
        desel_all_btn.clicked.connect(self.deselect_all)
        sel_bar.addWidget(desel_all_btn)

        sel_bar.addStretch()
        layout.addLayout(sel_bar)

        btn_bar = QHBoxLayout()
        discard_btn = QPushButton("Discard / Skip", self)
        discard_btn.clicked.connect(self.reject)
        btn_bar.addWidget(discard_btn)

        btn_bar.addStretch()

        import_sel_btn = QPushButton("Import Selected", self)
        import_sel_btn.clicked.connect(self.accept_selected)
        btn_bar.addWidget(import_sel_btn)

        import_all_btn = QPushButton("Import All", self)
        import_all_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        import_all_btn.clicked.connect(self.accept_all)
        btn_bar.addWidget(import_all_btn)

        layout.addLayout(btn_bar)

    def select_all(self):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Checked)

    def deselect_all(self):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.CheckState.Unchecked)

    def accept_all(self):
        self.approved_items = list(self.downloaded_items)
        self.accept()

    def accept_selected(self):
        self.approved_items = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.CheckState.Checked:
                self.approved_items.append(self.downloaded_items[r])
        self.accept()

    def save_state(self):
        prefs["review_dialog_width"] = self.width()
        prefs["review_dialog_height"] = self.height()
        try:
            prefs["review_table_header"] = bytes(
                self.table.horizontalHeader().saveState().toHex()
            ).decode("ascii")
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_state()
        super().closeEvent(event)

    def accept(self):
        self.save_state()
        super().accept()

    def reject(self):
        self.save_state()
        super().reject()



from qt.core import QStyledItemDelegate, QStyleOptionProgressBar, QStyle, QApplication, QPalette

class QueueProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() == 6:  # Progress column
            progress = index.data(Qt.ItemDataRole.UserRole)
            status = index.data(Qt.ItemDataRole.UserRole + 1)
            custom_label = index.data(Qt.ItemDataRole.UserRole + 2)

            if progress is None:
                super().paint(painter, option, index)
                return

            opts = QStyleOptionProgressBar()
            opts.rect = option.rect
            opts.minimum = 0
            opts.maximum = 100
            opts.progress = int(progress)
            
            # Determine text to display
            if status in ("Queued", "Queued (Bookracy)"):
                opts.text = status
                opts.textVisible = True
                opts.progress = 0
            elif status and ("downloaded" in status.lower() or "added" in status.lower()):
                opts.text = "100%"
                opts.textVisible = True
                opts.progress = 100
            elif status and ("failed" in status.lower() or "error" in status.lower() or "stopped" in status.lower()):
                opts.text = status
                opts.textVisible = True
                opts.progress = 0
            else:
                opts.text = custom_label if custom_label else f"{opts.progress}%"
                opts.textVisible = True

            QApplication.style().drawControl(QStyle.ControlElement.CE_ProgressBar, opts, painter)
        else:
            super().paint(painter, option, index)

class LibgenDialog(QDialog):
    def __init__(self, gui, initial_query=None, selected_books=None, parent=None):
        super().__init__(parent or gui)
        self.gui = gui
        self.initial_query = initial_query
        self.selected_books = list(selected_books) if selected_books else []
        self.setWindowTitle(f"LibGen Downloader ({PLUGIN_VERSION_STR})")
        saved_w = min(1150, max(850, int(prefs.get("dialog_width", 980))))
        saved_h = min(800, max(550, int(prefs.get("dialog_height", 620))))
        self.resize(saved_w, saved_h)

        self.search_results = []
        self.queue_manager = QueueManager()
        self.queue_manager.queue_updated.connect(self.update_queue_table)
        self.queue_manager.clear()
        self.mirror_health = {}
        self.session_cdn_speeds = {}
        self.download_worker = None
        self.search_worker = None
        self.search_queue_worker = None
        self.health_worker = None
        
        # Debounce timer for saving preferences
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self._do_save_all_field_preferences)

        # In-memory cover cache and text loading animation timer
        self.cover_cache = OrderedDict()
        self.cover_anim_timer = QTimer(self)
        self.cover_anim_timer.setInterval(110)
        self.cover_anim_timer.timeout.connect(self.update_cover_animation)
        self.cover_anim_frame = 0

        # Debounce timer for queue filtering
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self.apply_queue_filter)

        # Download stats and cats toggle (toggled by triple-clicking version badge)
        self.show_stats = bool(prefs.get("show_download_stats", False))
        self.show_cats = bool(prefs.get("show_cats", False))
        self.version_click_count = 0
        self.version_click_timer = QTimer(self)
        self.version_click_timer.setInterval(1200)
        self.version_click_timer.setSingleShot(True)
        self.version_click_timer.timeout.connect(self._reset_version_clicks)

        cleanup_expired_history()
        self._setup_ui()
        self.populate_mirrors_table()
        self.load_queue()

    def _setup_ui(self):
        base_layout = QHBoxLayout(self)
        
        left_widget = QWidget()
        main_layout = QVBoxLayout(left_widget)
        base_layout.addWidget(left_widget, stretch=5)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_layout.addWidget(QLabel("<b>Cover Preview</b>"))
        self.cover_label = QLabel("No Selection", self)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover_w = min(360, max(140, int(prefs.get("cover_panel_width", 200))))
        cover_h = min(520, max(180, int(prefs.get("cover_panel_height", 300))))
        self.cover_label.setFixedSize(cover_w, cover_h)
        self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")
        self.cover_label.setScaledContents(False)
        right_layout.addWidget(self.cover_label)

        self.side_neko_label = QLabel("(=^.^=) watching mirrors", self)
        self.side_neko_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.side_neko_label.setStyleSheet(
            "font-family: monospace; font-weight: 600; font-size: 12px; "
            "color: palette(text); padding: 4px; background: palette(base); "
            "border: 1px solid palette(mid); border-radius: 4px;"
        )
        self.side_neko_label.setVisible(self.show_cats)
        right_layout.addWidget(self.side_neko_label)

        self.side_mirror_header = QLabel("<b>🌐 Live Mirrors & CDNs</b>")
        self.side_mirror_header.setVisible(self.show_stats)
        right_layout.addWidget(self.side_mirror_header)

        self.side_mirror_status = QPlainTextEdit(self)
        self.side_mirror_status.setReadOnly(True)
        self.side_mirror_status.setFixedWidth(230)
        self.side_mirror_status.setStyleSheet(MONO_PANEL_STYLE)
        self.side_mirror_status.setVisible(self.show_stats)
        right_layout.addWidget(self.side_mirror_status)
        base_layout.addWidget(right_widget, stretch=1)


        # Top Panel: Clean Primary Search Bar + Collapsible Advanced Drawer
        top_panel = QVBoxLayout()
        top_panel.setSpacing(6)

        # --- Row 1 (Primary Search Controls: Unified Input + Backend Dropdown) ---
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 Search by title, author, or ISBN...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.start_search)
        if self.initial_query:
            self.search_input.setText(self.initial_query)
            self.search_input.selectAll()
        row1.addWidget(self.search_input, stretch=6)

        self.backend_combo = QComboBox(self)
        self.backend_combo.addItem("Backend: LibGen", "libgen")
        self.backend_combo.addItem("Backend: Bookracy", "bookracy")
        self.backend_combo.addItem("Backend: Dual Engine (Failover)", "dual")
        cur_bk = get_active_backend()
        for idx in range(self.backend_combo.count()):
            if self.backend_combo.itemData(idx) == cur_bk:
                self.backend_combo.setCurrentIndex(idx)
                break
        self.backend_combo.currentIndexChanged.connect(self.on_backend_changed)
        row1.addWidget(self.backend_combo, stretch=2)

        self.search_btn = QPushButton("Search", self)
        self.search_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.search_btn.clicked.connect(self.start_search)
        row1.addWidget(self.search_btn)

        self.stop_search_btn = QPushButton("Stop Search", self)
        self.stop_search_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.stop_search_btn.setVisible(False)
        self.stop_search_btn.clicked.connect(self.stop_search)
        row1.addWidget(self.stop_search_btn)

        self.toggle_filters_btn = QPushButton("⚙ Filters ▾", self)
        self.toggle_filters_btn.setToolTip("Toggle secondary search parameters (Format, Language, Field, Category, Mirror, History)")
        self.toggle_filters_btn.setStyleSheet("padding: 5px 10px;")
        self.toggle_filters_btn.clicked.connect(self.toggle_advanced_filters)
        row1.addWidget(self.toggle_filters_btn)

        top_panel.addLayout(row1)

        # --- Collapsible Advanced Drawer (Row 2) ---
        self.advanced_filters_widget = QWidget(self)
        self.advanced_filters_widget.setObjectName("advanced_filters_widget")
        self.advanced_filters_widget.setStyleSheet(
            "#advanced_filters_widget { background: palette(base); border: 1px solid palette(mid); border-radius: 6px; padding: 4px; }"
        )
        adv_vlayout = QVBoxLayout(self.advanced_filters_widget)
        adv_vlayout.setContentsMargins(8, 6, 8, 6)
        adv_vlayout.setSpacing(6)

        adv_row1 = QHBoxLayout()
        adv_row1.setSpacing(8)

        self.import_csv_btn = QPushButton("📄 Import CSV / List", self)
        self.import_csv_btn.setToolTip("Import books from Goodreads, StoryGraph, Hardcover, or custom CSV/TXT files containing ISBNs, Titles, and Authors")
        self.import_csv_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.import_csv_btn.clicked.connect(self.open_csv_import_dialog)
        adv_row1.addWidget(self.import_csv_btn)

        adv_row1.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(SUPPORTED_FORMATS)
        cur_fmt = prefs.get("preferred_format", "Any").upper()
        fmt_idx = self.format_combo.findText(cur_fmt)
        if fmt_idx >= 0:
            self.format_combo.setCurrentIndex(fmt_idx)
        self.format_combo.currentTextChanged.connect(self.save_all_field_preferences)
        self.format_combo.currentTextChanged.connect(lambda _: self.filter_results_table())
        adv_row1.addWidget(self.format_combo)

        adv_row1.addWidget(QLabel("Lang:"))
        self.lang_combo = CheckableComboBox(self)
        self.lang_combo.setMinimumWidth(85)
        saved_langs = prefs.get("preferred_languages")
        if not saved_langs:
            single = prefs.get("preferred_language", "English")
            saved_langs = [single] if single else ["English"]
        self.lang_combo.add_checkable_items(SUPPORTED_LANGUAGES, saved_langs)
        self.lang_combo.selection_changed.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.lang_combo)

        self.field_label = QLabel("Field:")
        adv_row1.addWidget(self.field_label)
        self.field_combo = QComboBox(self)
        self.field_combo.setMaximumWidth(120)
        self.field_combo.addItems(list(SEARCH_FIELDS.keys()))
        cur_field = prefs.get("search_field", "All Fields")
        f_idx = self.field_combo.findText(cur_field)
        if f_idx >= 0:
            self.field_combo.setCurrentIndex(f_idx)
        self.field_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.field_combo)

        self.category_label = QLabel("Cat:")
        adv_row1.addWidget(self.category_label)
        self.category_combo = QComboBox(self)
        self.category_combo.setMaximumWidth(140)
        self.category_combo.addItems(list(CATEGORIES.keys()))
        cur_cat = prefs.get("search_category", "All Categories")
        c_idx = self.category_combo.findText(cur_cat)
        if c_idx >= 0:
            self.category_combo.setCurrentIndex(c_idx)
        self.category_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.category_combo)

        adv_row1.addWidget(QLabel("Max:"))
        self.max_results_spinbox = QSpinBox(self)
        self.max_results_spinbox.setMaximumWidth(65)
        self.max_results_spinbox.setRange(1, 1000)
        self.max_results_spinbox.setValue(int(prefs.get("max_results", 5)))
        self.max_results_spinbox.valueChanged.connect(self.save_all_field_preferences)
        adv_row1.addWidget(self.max_results_spinbox)
        adv_row1.addStretch(1)
        adv_vlayout.addLayout(adv_row1)

        adv_row2 = QHBoxLayout()
        adv_row2.setSpacing(8)

        self.mirror_label = QLabel("Mirror:")
        adv_row2.addWidget(self.mirror_label)
        self.mirror_combo = QComboBox(self)
        self.mirror_combo.setMaximumWidth(150)
        self.update_mirror_combobox()
        self.mirror_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row2.addWidget(self.mirror_combo)

        self.fetch_mirrors_btn = QPushButton("Fetch Live")
        self.fetch_mirrors_btn.setToolTip("Fetch active mirrors from open-slum.org")
        self.fetch_mirrors_btn.clicked.connect(self.manual_fetch_mirrors)
        adv_row2.addWidget(self.fetch_mirrors_btn)

        self.filter_label = QLabel("Mode:")
        adv_row2.addWidget(self.filter_label)
        self.filter_combo = QComboBox(self)
        self.filter_combo.setMaximumWidth(110)
        self.filter_combo.addItems(FILTER_MODES)
        cur_mode = prefs.get("filter_mode", "Prioritize")
        m_idx = self.filter_combo.findText(cur_mode)
        if m_idx >= 0:
            self.filter_combo.setCurrentIndex(m_idx)
        self.filter_combo.currentTextChanged.connect(self.save_all_field_preferences)
        adv_row2.addWidget(self.filter_combo)

        self.unique_checkbox = QCheckBox("Unique", self)
        self.unique_checkbox.setToolTip("Filter out duplicate books (same title, author, and format)")
        self.unique_checkbox.setChecked(bool(prefs.get("unique_results", True)))
        self.unique_checkbox.stateChanged.connect(self.save_all_field_preferences)
        adv_row2.addWidget(self.unique_checkbox)

        self.history_checkbox = QCheckBox("History", self)
        self.history_checkbox.setToolTip(
            f"Opt-in: Save search queries to local file and enable autocomplete ({get_search_history_filepath()})"
        )
        self.history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
        self.history_checkbox.stateChanged.connect(self.on_history_toggled)
        adv_row2.addWidget(self.history_checkbox)

        self.history_settings_btn = QPushButton("⚙", self)
        self.history_settings_btn.setToolTip("Configure search & download history limits and auto-retention")
        self.history_settings_btn.setFixedWidth(26)
        self.history_settings_btn.clicked.connect(self.open_history_settings)
        adv_row2.addWidget(self.history_settings_btn)

        adv_row2.addStretch(1)
        adv_vlayout.addLayout(adv_row2)

        # Restore expanded/collapsed state from preferences
        show_adv = bool(prefs.get("show_advanced_filters", False))
        self.advanced_filters_widget.setVisible(show_adv)
        self.toggle_filters_btn.setText("⚙ Filters ▴" if show_adv else "⚙ Filters ▾")
        top_panel.addWidget(self.advanced_filters_widget)

        # Batch Calibre Records Search Queue Bar (if books selected from Calibre)
        self.search_queue_bar = QWidget(self)
        queue_bar_layout = QHBoxLayout(self.search_queue_bar)
        queue_bar_layout.setContentsMargins(8, 6, 8, 6)
        self.search_queue_bar.setStyleSheet(
            PANEL_STYLE
        )

        n_books = len(self.selected_books)
        self.start_queue_search_btn = QPushButton(
            f"📚 Search {n_books} Loaded Calibre Record(s) in Queue (1 match/book)", self
        )
        self.start_queue_search_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.start_queue_search_btn.clicked.connect(self.start_search_queue)
        queue_bar_layout.addWidget(self.start_queue_search_btn, stretch=1)


        self.pause_queue_search_btn = QPushButton("⏸ Pause", self)
        self.pause_queue_search_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.pause_queue_search_btn.setVisible(False)
        self.pause_queue_search_btn.setToolTip("Pause batch record search and retain remaining queue")
        self.pause_queue_search_btn.clicked.connect(self.pause_search_queue)
        queue_bar_layout.addWidget(self.pause_queue_search_btn)

        self.stop_queue_search_btn = QPushButton("Stop Queue Search", self)
        self.stop_queue_search_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.stop_queue_search_btn.setVisible(False)
        self.stop_queue_search_btn.clicked.connect(self.stop_search_queue)
        queue_bar_layout.addWidget(self.stop_queue_search_btn)

        self.dismiss_queue_bar_btn = QPushButton("✕", self)
        self.dismiss_queue_bar_btn.setToolTip("Dismiss Calibre records search queue")
        self.dismiss_queue_bar_btn.setFixedWidth(24)
        self.dismiss_queue_bar_btn.clicked.connect(self.dismiss_search_queue_bar)
        queue_bar_layout.addWidget(self.dismiss_queue_bar_btn)

        if not self.selected_books:
            self.search_queue_bar.setVisible(False)

        top_panel.addWidget(self.search_queue_bar)
        main_layout.addLayout(top_panel)
        self.setup_search_completer()

        # Tabs: Search Results, Queue, and Mirrors/Health
        self.tabs = QTabWidget(self)
        self.tabs.setMovable(True)
        self.tabs.currentChanged.connect(self.on_table_selection_changed)

        # --- Tab 1: Search Results ---
        self.tab_results = QWidget()
        self.tab_results.setObjectName("tab_results")
        results_layout = QVBoxLayout(self.tab_results)

        # Inline Search Progress & Active Mirror Display
        search_status_box = QHBoxLayout()
        self.search_mirror_label = QLabel("Search status: Ready", self)
        self.search_mirror_label.setStyleSheet("font-weight: 600; color: palette(highlight);")
        search_status_box.addWidget(self.search_mirror_label, stretch=2)

        self.search_progress_bar = QProgressBar(self)
        self.search_progress_bar.setFixedHeight(16)
        self.search_progress_bar.setMaximumWidth(300)
        self.search_progress_bar.setTextVisible(True)
        self.search_progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.search_progress_bar.setVisible(False)
        search_status_box.addWidget(self.search_progress_bar, stretch=1)

        results_layout.addLayout(search_status_box)

        self.results_table = QTableWidget(self)
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "Title", "Author", "Publisher / Year", "Language", "Format", "Size"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.results_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.results_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSortingEnabled(True)
        self.results_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.show_results_context_menu)
        results_layout.addWidget(self.results_table)

        # Global shortcut: Ctrl+Shift+A to add selected to queue
        self.queue_shortcut = QShortcut(QKeySequence("Ctrl+Shift+A"), self)
        self.queue_shortcut.activated.connect(self.queue_selected_results)

        # Results Bottom Buttons
        btn_bar = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All", self)
        self.select_all_btn.clicked.connect(self.select_all_results)
        btn_bar.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All", self)
        self.deselect_all_btn.clicked.connect(self.deselect_all_results)
        btn_bar.addWidget(self.deselect_all_btn)

        self.discard_selected_results_btn = QPushButton("Discard Selected", self)
        self.discard_selected_results_btn.clicked.connect(self.discard_selected_results)
        btn_bar.addWidget(self.discard_selected_results_btn)

        self.dedupe_results_btn = QPushButton("Remove Duplicates", self)
        self.dedupe_results_btn.setToolTip("Remove duplicate books from search results (matching detail URL, MD5, or title/format)")
        self.dedupe_results_btn.clicked.connect(self.dedupe_search_results)
        btn_bar.addWidget(self.dedupe_results_btn)

        self.clear_results_btn = QPushButton("Clear Results", self)
        self.clear_results_btn.setToolTip("Clear all search results")
        self.clear_results_btn.clicked.connect(self.clear_search_results)
        btn_bar.addWidget(self.clear_results_btn)

        btn_bar.addStretch()

        self.queue_selected_btn = QPushButton("Add to Queue", self)
        self.queue_selected_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.queue_selected_btn.clicked.connect(self.queue_selected_results)
        btn_bar.addWidget(self.queue_selected_btn)

        self.download_now_btn = QPushButton("Download Selected", self)
        self.download_now_btn.clicked.connect(self.download_selected_now)
        btn_bar.addWidget(self.download_now_btn)

        results_layout.addLayout(btn_bar)
        self.tabs.addTab(self.tab_results, "Search Results (0)")

        # --- Tab 2: Download Queue ---
        self.tab_queue = QWidget()
        self.tab_queue.setObjectName("tab_queue")
        queue_layout = QVBoxLayout(self.tab_queue)

        # Queue Segmentation: Queued, Downloading, Downloaded, Failed
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("View:"))
        self.queue_filter_mode = "Queued"
        self.queue_filter_btns = {}

        for mode in ("Queued", "Downloading", "Downloaded", "Failed"):
            btn = QPushButton(f"{mode} (0)", self)
            btn.setCheckable(True)
            if mode == "Queued":
                btn.setChecked(True)
                btn.setStyleSheet(FILTER_BUTTON_ACTIVE_STYLE)
            else:
                btn.setStyleSheet(FILTER_BUTTON_STYLE)
            btn.clicked.connect(lambda checked, m=mode: self.set_queue_filter(m))
            filter_bar.addWidget(btn)
            self.queue_filter_btns[mode] = btn

        filter_bar.addStretch(1)
        queue_layout.addLayout(filter_bar)

        # Dedicated Session / Overall Bulk Download Progress Bar
        self.bulk_progress_bar = QProgressBar(self)
        self.bulk_progress_bar.setFixedHeight(18)
        self.bulk_progress_bar.setTextVisible(True)
        self.bulk_progress_bar.setFormat("Bulk Download: Ready (0/0)")
        self.bulk_progress_bar.setStyleSheet(PROGRESS_BAR_STYLE)
        self.bulk_progress_bar.setVisible(False)
        queue_layout.addWidget(self.bulk_progress_bar)

        self.queue_table = QTableWidget(self)
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels([
            "Title", "Author", "Format", "Size", "Status", "Speed", "Progress"
        ])
        self.queue_table.setItemDelegateForColumn(6, QueueProgressDelegate(self.queue_table))
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.queue_table.setItemDelegateForColumn(6, ProgressBarDelegate(self.queue_table))
        queue_layout.addWidget(self.queue_table)

        # Collapsible Live Activity Log
        log_header_box = QHBoxLayout()
        self.log_toggle_btn = QPushButton("▶ Live Activity Log", self)
        self.log_toggle_btn.setFlat(True)
        self.log_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.log_toggle_btn.setStyleSheet("text-align: left; font-weight: 600; color: palette(text); font-size: 11px; padding: 2px;")
        self.log_toggle_btn.clicked.connect(self.toggle_activity_log)
        log_header_box.addWidget(self.log_toggle_btn)
        log_header_box.addStretch(1)
        queue_layout.addLayout(log_header_box)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        log_h = min(320, max(70, int(prefs.get("log_panel_height", 120))))
        self.log_view.setFixedHeight(log_h)
        self.log_view.setStyleSheet(MONO_PANEL_STYLE)
        self.log_view.setPlaceholderText("Live download events, mirror cycles, and streaming chunks will appear here...")
        self.log_view.setVisible(False)
        queue_layout.addWidget(self.log_view)

        # Queue Bottom Buttons (Two compact rows)
        q_row1 = QHBoxLayout()
        self.clear_downloaded_btn = QPushButton("Clear Finished", self)
        self.clear_downloaded_btn.setToolTip("Remove downloaded / completed items from queue")
        self.clear_downloaded_btn.clicked.connect(self.clear_downloaded_items)
        q_row1.addWidget(self.clear_downloaded_btn)

        self.remove_queue_btn = QPushButton("Remove Selected", self)
        self.remove_queue_btn.clicked.connect(self.remove_from_queue)
        q_row1.addWidget(self.remove_queue_btn)

        self.clear_queue_btn = QPushButton("Clear Queue", self)
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        q_row1.addWidget(self.clear_queue_btn)

        self.dedupe_queue_btn = QPushButton("Remove Duplicates", self)
        self.dedupe_queue_btn.setToolTip("Remove duplicate items from download queue (matching detail URL, MD5, or title/author)")
        self.dedupe_queue_btn.clicked.connect(self.dedupe_download_queue)
        q_row1.addWidget(self.dedupe_queue_btn)

        self.retry_failed_btn = QPushButton("Retry Failed", self)
        self.retry_failed_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.retry_failed_btn.clicked.connect(self.retry_failed_downloads)
        q_row1.addWidget(self.retry_failed_btn)

        self.retry_bookracy_btn = QPushButton("Retry with Bookracy", self)
        self.retry_bookracy_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.retry_bookracy_btn.setToolTip("Reroute failed or pending downloads directly through Bookracy")
        self.retry_bookracy_btn.clicked.connect(self.retry_failed_with_bookracy)
        q_row1.addWidget(self.retry_bookracy_btn)

        q_row1.addWidget(QLabel("Concurrent Files:"))
        self.concurrency_spinbox = QSpinBox(self)
        self.concurrency_spinbox.setRange(1, 4)
        self.concurrency_spinbox.setValue(int(prefs.get("concurrent_downloads", 1)))
        self.concurrency_spinbox.setToolTip("Number of books downloaded at the same time (default 1 for maximum speed and zero rate-limiting)")
        self.concurrency_spinbox.valueChanged.connect(self.save_all_field_preferences)
        q_row1.addWidget(self.concurrency_spinbox)

        q_row1.addStretch(1)
        queue_layout.addLayout(q_row1)


        q_row2 = QHBoxLayout()
        self.fast_mode_checkbox = QCheckBox("⚡ Fast Mode", self)
        self.fast_mode_checkbox.setToolTip("Fast Mode: 3s mirror probe, skips dead/troubled downloads immediately to Failed list")
        self.fast_mode_checkbox.setChecked(bool(prefs.get("fast_mode", False)))
        self.fast_mode_checkbox.stateChanged.connect(self.save_all_field_preferences)
        q_row2.addWidget(self.fast_mode_checkbox)

        self.auto_retry_checkbox = QCheckBox("Auto-retry until all downloaded", self)
        self.auto_retry_checkbox.setChecked(False)
        q_row2.addWidget(self.auto_retry_checkbox)

        self.bookracy_fallback_checkbox = QCheckBox("Bookracy Fallback", self)
        self.bookracy_fallback_checkbox.setToolTip("Automatically retry failed LibGen downloads with Bookracy")
        self.bookracy_fallback_checkbox.setChecked(bool(prefs.get("bookracy_auto_retry_failed", True)))
        self.bookracy_fallback_checkbox.stateChanged.connect(self._toggle_bookracy_fallback)
        q_row2.addWidget(self.bookracy_fallback_checkbox)

        q_row2.addWidget(QLabel("After:"))
        self.download_action_combo = QComboBox(self)
        self.download_action_combo.addItems(["Import to Calibre", "Save to Folder"])
        action_idx = self.download_action_combo.findText(prefs.get("download_action", "Import to Calibre"))
        if action_idx >= 0:
            self.download_action_combo.setCurrentIndex(action_idx)
        self.download_action_combo.currentTextChanged.connect(self.save_all_field_preferences)
        q_row2.addWidget(self.download_action_combo)

        self.download_dir_btn = QPushButton("Folder...", self)
        self.download_dir_btn.setToolTip("Choose where downloaded files are saved")
        self.download_dir_btn.clicked.connect(self.choose_download_directory)
        q_row2.addWidget(self.download_dir_btn)

        q_row2.addStretch(1)

        self.pause_download_btn = QPushButton("⏸ Pause Download", self)
        self.pause_download_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.pause_download_btn.setVisible(False)
        self.pause_download_btn.setToolTip("Pause downloading and retain remaining queued items")
        self.pause_download_btn.clicked.connect(self.pause_bulk_download)
        q_row2.addWidget(self.pause_download_btn)

        self.stop_download_btn = QPushButton("Stop Download", self)
        self.stop_download_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.clicked.connect(self.stop_bulk_download)
        q_row2.addWidget(self.stop_download_btn)

        self.start_download_btn = QPushButton("Start Bulk Download", self)
        self.start_download_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.start_download_btn.clicked.connect(lambda: self.start_bulk_download())
        q_row2.addWidget(self.start_download_btn)

        queue_layout.addLayout(q_row2)
        self.tabs.addTab(self.tab_queue, "Downloads (0)")


        # --- Tab 3: Mirrors & Health ---
        self.tab_mirrors = QWidget()
        self.tab_mirrors.setObjectName("tab_mirrors")
        mirrors_layout = QVBoxLayout(self.tab_mirrors)

        # Mirrors Table
        self.mirrors_table = QTableWidget(self)
        self.mirrors_table.setColumnCount(6)
        self.mirrors_table.setHorizontalHeaderLabels([
            "Mirror URL", "Status", "Latency", "Speed", "Type", "Action"
        ])
        self.mirrors_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.mirrors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        mirrors_layout.addWidget(self.mirrors_table)

        # Mirror Controls
        mirror_actions_bar = QHBoxLayout()
        self.test_all_mirrors_btn = QPushButton("Ping / Test All Mirrors", self)
        self.test_all_mirrors_btn.clicked.connect(self.test_all_mirrors)
        mirror_actions_bar.addWidget(self.test_all_mirrors_btn)

        self.sort_speed_btn = QPushButton("Sort by Speed", self)
        self.sort_speed_btn.setStyleSheet("font-weight: bold;")
        self.sort_speed_btn.clicked.connect(self.sort_mirrors_by_speed)
        mirror_actions_bar.addWidget(self.sort_speed_btn)

        self.set_primary_btn = QPushButton("Set Selected as Primary", self)
        self.set_primary_btn.clicked.connect(self.set_selected_mirror_primary)
        mirror_actions_bar.addWidget(self.set_primary_btn)

        self.discard_dead_btn = QPushButton("Discard Dead Mirrors", self)
        self.discard_dead_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
        self.discard_dead_btn.setToolTip("Remove mirrors that failed latency/bandwidth tests from your configured mirrors")
        self.discard_dead_btn.clicked.connect(self.discard_dead_mirrors)
        mirror_actions_bar.addWidget(self.discard_dead_btn)

        mirror_actions_bar.addStretch()
        mirrors_layout.addLayout(mirror_actions_bar)

        # Add Custom Mirror Box
        add_group = QGroupBox("Add Custom Mirror")
        add_layout = QHBoxLayout(add_group)
        self.add_mirror_input = QLineEdit(self)
        self.add_mirror_input.setPlaceholderText("https://libgen.is or custom mirror URL...")
        self.add_mirror_input.returnPressed.connect(self.add_custom_mirror_handler)
        add_layout.addWidget(self.add_mirror_input, stretch=3)

        self.add_mirror_btn = QPushButton("Add Mirror", self)
        self.add_mirror_btn.clicked.connect(self.add_custom_mirror_handler)
        add_layout.addWidget(self.add_mirror_btn)

        mirrors_layout.addWidget(add_group)
        self.tabs.addTab(self.tab_mirrors, "Mirrors & Health")

        main_layout.addWidget(self.tabs)

        # Bottom Progress & Status Bar
        status_bar = QHBoxLayout()
        self.status_label = QLabel("Ready", self)
        status_bar.addWidget(self.status_label, stretch=2)



        # ASCII Cat (Neko) Animation Label
        self.neko_label = QLabel("(=^.^=)zZ", self)
        self.neko_label.setFixedWidth(85)
        self.neko_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.neko_label.setStyleSheet("font-family: monospace; font-weight: 600; font-size: 13px; color: palette(text);")
        self.neko_label.setVisible(self.show_cats)
        status_bar.addWidget(self.neko_label)

        self.neko_timer = QTimer(self)
        self.neko_timer.timeout.connect(self.update_neko_animation)
        self.neko_frame_idx = 0
        self.neko_timer.start(400)

        # Version Badge in Status Bar (Click 3x to toggle hidden download stats, Right-click for API Backend selection)
        self.version_badge = QLabel(PLUGIN_VERSION_STR, self)
        self.version_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_badge.mousePressEvent = self.on_version_badge_clicked
        self.version_badge.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.version_badge.customContextMenuRequested.connect(self.show_backend_context_menu)
        self._update_version_badge_style()
        status_bar.addWidget(self.version_badge)

        main_layout.addLayout(status_bar)

        self.toast = ToastOverlay(self)

        self.restore_header_states()
        self.update_pending_combo()
        self.update_backend_ui_visibility()

    def update_pending_combo(self):
        if not hasattr(self, "pending_combo"):
            return
        pending = get_pending_searches()
        self.pending_combo.blockSignals(True)
        self.pending_combo.clear()
        if not pending:
            self.pending_combo.addItem("None (0)")
            self.pending_combo.setEnabled(False)
            if hasattr(self, "pending_clear_btn"):
                self.pending_clear_btn.setEnabled(False)
            if hasattr(self, "pending_widget"):
                self.pending_widget.setVisible(False)
        else:
            self.pending_combo.addItem(f"Pending ({len(pending)})...", None)
            for p in pending:
                display_p = p if len(p) <= 24 else (p[:21] + "...")
                self.pending_combo.addItem(display_p, p)
            self.pending_combo.setEnabled(True)
            if hasattr(self, "pending_clear_btn"):
                self.pending_clear_btn.setEnabled(True)
            if hasattr(self, "pending_widget"):
                self.pending_widget.setVisible(True)
        self.pending_combo.blockSignals(False)

    def on_pending_selected(self, idx):
        if idx <= 0:
            return
        query = self.pending_combo.currentData()
        if query:
            self.search_input.setText(query)
            self.search_input.selectAll()

    def remove_selected_pending(self):
        idx = self.pending_combo.currentIndex()
        if idx > 0:
            query = self.pending_combo.currentData()
            if query:
                remove_pending_search(query)
                self.update_pending_combo()

    def open_csv_import_dialog(self):
        dlg = CsvImportDialog(self)
        dlg.exec()

    def set_tab_text_for_widget(self, widget, text):
        if hasattr(self, "tabs") and widget is not None:
            idx = self.tabs.indexOf(widget)
            if idx >= 0:
                self.tabs.setTabText(idx, text)

    def set_current_tab_widget(self, widget):
        if hasattr(self, "tabs") and widget is not None:
            idx = self.tabs.indexOf(widget)
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)

    def save_header_states(self):
        try:
            if hasattr(self, "results_table"):
                prefs["results_table_header"] = bytes(self.results_table.horizontalHeader().saveState().toHex()).decode("ascii")
            if hasattr(self, "queue_table"):
                prefs["queue_table_header"] = bytes(self.queue_table.horizontalHeader().saveState().toHex()).decode("ascii")
            if hasattr(self, "mirrors_table"):
                prefs["mirrors_table_header"] = bytes(self.mirrors_table.horizontalHeader().saveState().toHex()).decode("ascii")
            if hasattr(self, "tabs"):
                order = []
                for i in range(self.tabs.count()):
                    w = self.tabs.widget(i)
                    name = w.objectName() if w else ""
                    if name:
                        order.append(name)
                if order:
                    prefs["tabs_order"] = order
            if hasattr(self, "cover_label"):
                prefs["cover_panel_width"] = self.cover_label.width()
                prefs["cover_panel_height"] = self.cover_label.height()
            if hasattr(self, "log_view"):
                prefs["log_panel_height"] = self.log_view.height()
        except Exception as e:
            print(f"[LibGen Plugin] Failed to save header states: {e}")

    def restore_header_states(self):
        try:
            for key, table in [
                ("results_table_header", getattr(self, "results_table", None)),
                ("queue_table_header", getattr(self, "queue_table", None)),
                ("mirrors_table_header", getattr(self, "mirrors_table", None)),
            ]:
                if table and prefs.get(key):
                    state_hex = prefs.get(key)
                    table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode("ascii")))

            if hasattr(self, "tabs") and prefs.get("tabs_order"):
                saved_order = prefs.get("tabs_order")
                named_widgets = {
                    "tab_results": getattr(self, "tab_results", None),
                    "tab_queue": getattr(self, "tab_queue", None),
                    "tab_mirrors": getattr(self, "tab_mirrors", None),
                }
                for target_pos, name in enumerate(saved_order):
                    widget = named_widgets.get(name)
                    if widget:
                        current_pos = self.tabs.indexOf(widget)
                        if current_pos >= 0 and current_pos != target_pos:
                            tab_bar = self.tabs.tabBar()
                            if tab_bar:
                                tab_bar.moveTab(current_pos, target_pos)
        except Exception as e:
            print(f"[LibGen Plugin] Failed to restore header states: {e}")

    def _reset_version_clicks(self):
        self.version_click_count = 0

    def on_version_badge_clicked(self, event):
        if event and event.button() == Qt.MouseButton.RightButton:
            self.show_backend_context_menu(event.pos())
            return
        self.version_click_count += 1
        self.version_click_timer.start()
        if self.version_click_count >= 3:
            self.version_click_count = 0
            self.version_click_timer.stop()
            self.show_stats = not self.show_stats
            self.show_cats = self.show_stats
            prefs["show_download_stats"] = self.show_stats
            prefs["show_cats"] = self.show_cats
            self._update_version_badge_style()
            if hasattr(self, "neko_label"):
                self.neko_label.setVisible(self.show_cats)
            if hasattr(self, "side_neko_label"):
                self.side_neko_label.setVisible(self.show_cats)
            if hasattr(self, "side_mirror_header"):
                self.side_mirror_header.setVisible(self.show_stats)
            if hasattr(self, "side_mirror_status"):
                self.side_mirror_status.setVisible(self.show_stats)
            status_msg = "enabled" if self.show_stats else "disabled"
            self.status_label.setText(f"Cats and stats {status_msg}.")
            self.append_log(f"[CONFIG] Cats and download stats {status_msg} (toggled via version badge).")
            if hasattr(self, "toast"):
                toast_icon = "🐾" if self.show_stats else "🙈"
                self.toast.show_toast(f"{toast_icon} Cats, Stats & Mirror Panel {status_msg.capitalize()}")


    def _update_version_badge_style(self):
        if not hasattr(self, "version_badge"):
            return
        if self.show_stats:
            self.version_badge.setStyleSheet(
                "color: palette(highlight); font-size: 11px; padding: 2px 6px; background: palette(base); border: 1px solid palette(highlight); border-radius: 3px; font-weight: 600;"
            )
            self.version_badge.setToolTip("Cats & download statistics active (Click 3x to hide)")
        else:
            self.version_badge.setStyleSheet(
                "color: palette(text); font-size: 11px; padding: 2px 6px; background: palette(base); border: 1px solid palette(mid); border-radius: 3px;"
            )
            self.version_badge.setToolTip("Version info (Click 3x for cats/stats | Right-click for Backend)")

    def show_backend_context_menu(self, pos):
        from qt.core import QMenu, QAction
        menu = QMenu(self)
        menu.setTitle("⚡ API Backend Selection")

        try:
            from calibre_plugins.libgen_store.config import get_active_backend, BACKENDS
        except Exception:
            from config import get_active_backend, BACKENDS

        cur_backend = get_active_backend()

        for code, label in BACKENDS.items():
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(code == cur_backend)
            action.triggered.connect(lambda checked, b=code, title=label: self.switch_api_backend(b, title))
            menu.addAction(action)

        menu.exec(self.version_badge.mapToGlobal(pos))

    def switch_api_backend(self, backend_code, title):
        try:
            from calibre_plugins.libgen_store.config import set_active_backend
        except Exception:
            from config import set_active_backend
        set_active_backend(backend_code)
        if hasattr(self, "backend_combo"):
            for idx in range(self.backend_combo.count()):
                if self.backend_combo.itemData(idx) == backend_code:
                    self.backend_combo.blockSignals(True)
                    self.backend_combo.setCurrentIndex(idx)
                    self.backend_combo.blockSignals(False)
                    break
        self.update_mirror_combobox()
        self.update_backend_ui_visibility()
        self.append_log(f"[CONFIG] Switched active API backend to: {title}")
        if hasattr(self, "toast"):
            self.toast.show_toast(f"⚡ Backend: {title}")

    def update_backend_ui_visibility(self):
        try:
            from calibre_plugins.libgen_store.config import get_active_backend
        except Exception:
            from config import get_active_backend

        backend = get_active_backend()
        is_bookracy = (backend == "bookracy")

        # Hide/show LibGen specific controls in advanced drawer
        if hasattr(self, "field_label"):
            self.field_label.setVisible(not is_bookracy)
        if hasattr(self, "field_combo"):
            self.field_combo.setVisible(not is_bookracy)
        if hasattr(self, "category_label"):
            self.category_label.setVisible(not is_bookracy)
        if hasattr(self, "category_combo"):
            self.category_combo.setVisible(not is_bookracy)
        if hasattr(self, "mirror_label"):
            self.mirror_label.setVisible(not is_bookracy)
        if hasattr(self, "mirror_combo"):
            self.mirror_combo.setVisible(not is_bookracy)
        if hasattr(self, "fetch_mirrors_btn"):
            self.fetch_mirrors_btn.setVisible(not is_bookracy)
        if hasattr(self, "filter_label"):
            self.filter_label.setVisible(not is_bookracy)
        if hasattr(self, "filter_combo"):
            self.filter_combo.setVisible(not is_bookracy)

        # Hide/show Bookracy Fallback checkbox on Queue tab (only relevant for LibGen/Dual modes)
        if hasattr(self, "bookracy_fallback_checkbox"):
            self.bookracy_fallback_checkbox.setVisible(not is_bookracy)
        if hasattr(self, "retry_bookracy_btn"):
            self.retry_bookracy_btn.setVisible(not is_bookracy)

        # Hide/show 'Mirrors & Health' tab when in Bookracy mode
        if hasattr(self, "tabs") and hasattr(self, "tab_mirrors"):
            m_idx = self.tabs.indexOf(self.tab_mirrors)
            if is_bookracy and m_idx >= 0:
                self.tabs.removeTab(m_idx)
            elif not is_bookracy and m_idx < 0:
                self.tabs.addTab(self.tab_mirrors, "Mirrors & Health")

    def manual_fetch_mirrors(self):
        self.fetch_mirrors_btn.setEnabled(False)
        self.fetch_mirrors_btn.setText("Fetching...")
        
        self.live_mirror_worker = LiveMirrorWorker(parent=self)
        self.live_mirror_worker.mirrors_discovered.connect(self.on_manual_mirrors_discovered)
        self.live_mirror_worker.start()

    def on_manual_mirrors_discovered(self, live_mirrors):
        self.fetch_mirrors_btn.setEnabled(True)
        self.fetch_mirrors_btn.setText("Fetch Live")
        
        if live_mirrors:
            fallback_str = prefs.get("fallback_mirrors", "")
            fallbacks = [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip()]
            added = False
            for m in live_mirrors:
                if m not in fallbacks:
                    fallbacks.append(m)
                    added = True
            
            if added:
                prefs["fallback_mirrors"] = ", ".join(fallbacks)
                self.update_mirror_combobox()
                self.populate_mirrors_table()
                QMessageBox.information(self, "Mirrors Found", f"Successfully fetched and added new active mirrors from open-slum.org!")
            else:
                QMessageBox.information(self, "Mirrors Found", "Fetched live mirrors, but you already have them all in your configuration.")
        else:
            QMessageBox.warning(self, "Fetch Failed", "Could not fetch live mirrors or none were found active.")
    def update_mirror_combobox(self):
        self.mirror_combo.clear()
        self.mirror_combo.addItem("Auto (Best Latency)")
        for m in get_mirrors():
            self.mirror_combo.addItem(m)

        cur_selected = prefs.get("selected_mirror", "Auto")
        if cur_selected == "Auto" or str(cur_selected).startswith("Auto"):
            self.mirror_combo.setCurrentIndex(0)
        else:
            idx = self.mirror_combo.findText(cur_selected)
            if idx >= 0:
                self.mirror_combo.setCurrentIndex(idx)

    def update_neko_animation(self):
        is_active = False
        if hasattr(self, 'search_worker') and self.search_worker and self.search_worker.isRunning():
            is_active = True
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            is_active = True
            
        status_text = self.status_label.text().lower()
        is_error = "error" in status_text or "failed" in status_text or "aborted" in status_text
            
        if is_active:
            frames = ["(=O.O=) _/", "(=O.O=) _|", "(=O.O=) _~", "(=O.O=) _|"]
        elif is_error:
            frames = ["(=>_<=) !!", "(=>_<=)   "]
        else:
            frames = ["(=^.^=) zZ", "(=^.^=)  z", "(=^.^=)   ", "(=^.^=)zZ "]

        if not hasattr(self, 'neko_frame_idx'):
            self.neko_frame_idx = 0
            
        self.neko_frame_idx = (self.neko_frame_idx + 1) % max(len(frames), 10)
        
        if hasattr(self, 'neko_label'):
            self.neko_label.setText(frames[self.neko_frame_idx % len(frames)])
        if hasattr(self, 'side_neko_label'):
            side_frames = [
                "(=^.^=) scanning",
                "(=^.^=) scanning.",
                "(=^.^=) scanning..",
                "(=^.^=) scanning...",
            ] if is_active else [
                "(=^.^=) watching mirrors",
                "(= -.-=) watching mirrors",
                "(=^.^=) watching mirrors",
                "(= o.o=) watching mirrors",
            ]
            if is_error:
                side_frames = ["(=>_<=) check log", "(=>_<=) check log."]
            self.side_neko_label.setText(side_frames[self.neko_frame_idx % len(side_frames)])
            
        if hasattr(self, 'search_worker') and self.search_worker and self.search_worker.isRunning():
            spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spin_idx = self.neko_frame_idx % len(spinners)
            base_text = self.search_mirror_label.text()
            if len(base_text) > 2 and base_text[0] in spinners:
                base_text = base_text[2:]
            self.search_mirror_label.setText(f"{spinners[spin_idx]} {base_text}")


    # --- Cover Preview Handlers ---
    def on_table_selection_changed(self):
        # Determine which table triggered this if we want, or just check the active tab
        idx = self.tabs.currentIndex()
        book = None
        if idx == 0:
            rows = self.get_selected_result_rows()
            if rows:
                book = self.search_results[rows[0]]
        elif idx == 1:
            rows = sorted([item.row() for item in self.queue_table.selectedItems()])
            if rows:
                row = rows[0]
                if row < len(self.queue_manager):
                    book = self.queue_manager[row]["book"]
        
        if book and getattr(book, "detail_url", None):
            cache_key = book.detail_url or book.title
            if cache_key in self.cover_cache:
                self.cover_cache.move_to_end(cache_key)
                if hasattr(self, 'cover_worker') and self.cover_worker and self.cover_worker.isRunning():
                    self.cover_worker.abort()
                self.cover_anim_timer.stop()
                self._display_cover_pixmap(self.cover_cache[cache_key])
                return

            if hasattr(self, 'cover_worker') and self.cover_worker and self.cover_worker.isRunning():
                self.cover_worker.abort()

            # Start smooth animated text loading indicator
            self.cover_anim_frame = 0
            self.cover_anim_timer.start(110)
            self.update_cover_animation()

            self.cover_worker = CoverFetchWorker(book, parent=self)
            self.cover_worker.cover_fetched.connect(self.on_cover_fetched)
            self.cover_worker.cover_failed.connect(self.on_cover_failed)
            self.cover_worker.start()
        else:
            if hasattr(self, 'cover_worker') and self.cover_worker and self.cover_worker.isRunning():
                self.cover_worker.abort()
            self.cover_anim_timer.stop()
            self.cover_label.clear()
            self.cover_label.setText('<div align="center" style="font-family: monospace;"><div style="font-size: 22px; margin-bottom: 6px;">(=^.^=)</div><div style="font-family: sans-serif; font-size: 12px;">Select a book to preview</div></div>')
            self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")

    def update_cover_animation(self):
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        dots = [".  ", ".. ", "...", "   "]
        self.cover_anim_frame = getattr(self, 'cover_anim_frame', 0) + 1
        spin = spinners[self.cover_anim_frame % len(spinners)]
        dot = dots[(self.cover_anim_frame // 2) % len(dots)]

        html = f"""
        <div align="center" style="font-family: sans-serif;">
            <div style="font-family: monospace; font-size: 22px; margin-bottom: 8px;">(=O.O=)</div>
            <div style="font-size: 13px; font-weight: bold;">Loading Cover{dot}</div>
            <div style="font-size: 18px; margin-top: 10px; font-family: monospace;">{spin}</div>
        </div>
        """
        self.cover_label.setText(html)
        self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")

    def _display_cover_pixmap(self, data):
        from qt.core import QPixmap
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            scaled_pixmap = pixmap.scaled(
                self.cover_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.cover_label.clear()
            self.cover_label.setPixmap(scaled_pixmap)
            self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")
        else:
            self.on_cover_failed("")

    def on_cover_fetched(self, data, detail_url):
        if detail_url:
            self.cover_cache[detail_url] = data
            self.cover_cache.move_to_end(detail_url)
            while len(self.cover_cache) > 100:
                self.cover_cache.popitem(last=False)

        # Check if the fetched cover still matches the currently selected book
        idx = self.tabs.currentIndex()
        curr_book = None
        if idx == 0:
            rows = self.get_selected_result_rows()
            if rows:
                curr_book = self.search_results[rows[0]]
        elif idx == 1:
            rows = sorted([item.row() for item in self.queue_table.selectedItems()])
            if rows and rows[0] < len(self.queue_manager):
                curr_book = self.queue_manager[rows[0]]["book"]

        curr_url = getattr(curr_book, "detail_url", "")
        if curr_url == detail_url or not curr_url:
            self.cover_anim_timer.stop()
            self._display_cover_pixmap(data)

    def on_cover_failed(self, detail_url=""):
        self.cover_anim_timer.stop()
        self.cover_label.clear()
        self.cover_label.setText('<div align="center" style="font-family: monospace;"><div style="font-size: 22px; margin-bottom: 6px;">(= -.-=)</div><div style="font-family: sans-serif; font-size: 12px;">No Cover Available</div></div>')
        self.cover_label.setStyleSheet("background: palette(base); border: 1px solid palette(mid); color: palette(text);")

    def setup_search_completer(self):
        """Sets up or clears QCompleter based on whether local search history is enabled."""
        if hasattr(self, "search_input") and prefs.get("save_search_history", False):
            history = get_search_history()
            if history:
                seen = set()
                unique_hist = []
                for q in reversed(history):
                    if q not in seen:
                        seen.add(q)
                        unique_hist.append(q)
                completer = QCompleter(unique_hist, self)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                self.search_input.setCompleter(completer)
                return
        if hasattr(self, "search_input"):
            self.search_input.setCompleter(None)

    def on_history_toggled(self, state):
        if hasattr(self, "history_checkbox"):
            prefs["save_search_history"] = self.history_checkbox.isChecked()
            self.setup_search_completer()

    def open_history_settings(self):
        dlg = HistorySettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if hasattr(self, "history_checkbox"):
                self.history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
            self.setup_search_completer()

    def toggle_advanced_filters(self):
        if not hasattr(self, "advanced_filters_widget"):
            return
        new_state = not self.advanced_filters_widget.isVisible()
        self.advanced_filters_widget.setVisible(new_state)
        if hasattr(self, "toggle_filters_btn"):
            self.toggle_filters_btn.setText("⚙ Filters ▴" if new_state else "⚙ Filters ▾")
        prefs["show_advanced_filters"] = new_state

    def on_backend_changed(self, idx):
        if hasattr(self, "backend_combo"):
            bk_data = self.backend_combo.itemData(idx)
            if bk_data:
                set_active_backend(bk_data)
                self.update_mirror_combobox()
                self.update_backend_ui_visibility()
                name = BACKENDS.get(bk_data, bk_data)
                m_count = len(get_mirrors())
                self.status_label.setText(f"Active backend set to {name} ({m_count} mirror{'s' if m_count != 1 else ''})")
                self.append_log(f"[CONFIG] Switched active API backend to: {name}")
                if hasattr(self, "toast"):
                    self.toast.show_toast(f"⚡ Backend: {name}")

    # --- Search Handlers ---
    def start_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        append_search_history(query)
        self.setup_search_completer()
        self.search_results = []
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), "Search Results (0)")

        self.search_btn.setVisible(False)
        self.stop_search_btn.setVisible(True)
        self.stop_search_btn.setEnabled(True)
        self.stop_search_btn.setText("Stop Search")

        cur_bk = get_active_backend()
        bk_label = "Bookracy" if cur_bk == "bookracy" else ("Dual Engine" if cur_bk == "dual" else "LibGen")

        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(True)
            self.search_progress_bar.setRange(0, 0)
            self.search_progress_bar.setFormat(f"Searching {bk_label} for '{query}'...")

        self.status_label.setText(f"Searching {bk_label} for '{query}'...")
        self.search_mirror_label.setText(f"Connecting to {bk_label} for '{query}'...")

        # Update saved preferences
        field_text = self.field_combo.currentText().strip()
        field_code = SEARCH_FIELDS.get(field_text, "")
        selected_mirror = self.mirror_combo.currentText().strip()
        if selected_mirror.startswith("Auto"):
            selected_mirror = "Auto"

        prefs["search_field"] = field_text
        prefs["selected_mirror"] = selected_mirror
        prefs["preferred_languages"] = self.lang_combo.checked_items()
        prefs["preferred_language"] = ", ".join(self.lang_combo.checked_items())
        prefs["preferred_format"] = self.format_combo.currentText().strip()
        prefs["filter_mode"] = self.filter_combo.currentText().strip()
        prefs["unique_results"] = self.unique_checkbox.isChecked()

        cat_text = self.category_combo.currentText().strip()
        cat_code = CATEGORIES.get(cat_text, "")
        prefs["search_category"] = cat_text

        self.search_worker = SearchWorker(
            query=query,
            search_field=field_code,
            category=cat_code,
            selected_mirror=selected_mirror,
            language=self.lang_combo.checked_items(),
            fmt=self.format_combo.currentText().strip(),
            filter_mode=self.filter_combo.currentText().strip(),
            max_results=self.max_results_spinbox.value(),
            unique_results=self.unique_checkbox.isChecked(),
            parent=self,
        )
        self.search_worker.progress_signal.connect(self.on_search_progress)
        self.search_worker.partial_results_signal.connect(self.on_search_partial_results)
        self.search_worker.finished_signal.connect(self.on_search_finished)
        self.search_worker.error_signal.connect(self.on_search_error)
        self.search_worker.start()

    def stop_search(self):
        if hasattr(self, "search_worker") and self.search_worker and self.search_worker.isRunning():
            self.stop_search_btn.setEnabled(False)
            self.stop_search_btn.setText("Stopping...")
            self.status_label.setText("Search stopped by user.")
            self.search_mirror_label.setText("Search stopped by user.")
            self.search_worker.abort()
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)
        self.stop_search_btn.setVisible(False)
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)

    def on_search_progress(self, idx, total, mirror, found_count=0, target_count=0):
        host = urlparse(mirror).netloc or mirror
        percent = int(((idx - 1) / total) * 100) if total > 0 else 0

        if target_count > 0:
            msg = f"Querying mirrors [{idx}/{total}] • 📦 {found_count}/{target_count} artifacts found ({host})"
            self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({found_count})")
            if hasattr(self, "search_progress_bar"):
                self.search_progress_bar.setVisible(True)
                self.search_progress_bar.setRange(0, target_count)
                self.search_progress_bar.setValue(found_count)
                self.search_progress_bar.setFormat(f"Found {found_count}/{target_count} ({host})")
        else:
            msg = f"Querying mirror [{idx}/{total}]: {host} ({mirror})"
            if hasattr(self, "search_progress_bar"):
                self.search_progress_bar.setVisible(True)
                self.search_progress_bar.setRange(0, total)
                self.search_progress_bar.setValue(idx)
                self.search_progress_bar.setFormat(f"Mirror {idx}/{total}: {host}")

        self.status_label.setText(msg)
        self.status_label.setToolTip(mirror)
        self.search_mirror_label.setText(msg)

    def on_search_partial_results(self, books, mirror):
        self.search_results = list(books or [])
        self.populate_results_table()
        count = len(self.search_results)
        host = urlparse(mirror).netloc or mirror or "mirror"
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({count})")
        self.search_mirror_label.setText(f"Showing {count} live result(s) from {host}...")

    def on_search_finished(self, books, mirror_used=""):
        self.search_results = books
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)
        self.stop_search_btn.setVisible(False)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

        host = urlparse(mirror_used).netloc if mirror_used else "mirror"
        success_text = f"✓ Found {len(books)} artifacts via {host}." if mirror_used else f"✓ Found {len(books)} artifacts."
        self.status_label.setText(success_text)
        self.search_mirror_label.setText(success_text)
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(books)})")
        self.set_current_tab_widget(getattr(self, "tab_results", None))
        self.populate_results_table()

        query = self.search_input.text().strip()
        if not books and query:
            add_pending_search(query)
            self.update_pending_combo()
        elif books and query:
            remove_pending_search(query)
            self.update_pending_combo()

    def on_search_error(self, err_msg):
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)
        self.stop_search_btn.setVisible(False)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

        self.status_label.setText(f"Search failed: {err_msg}")
        self.search_mirror_label.setText(f"Search failed: {err_msg}")

        query = self.search_input.text().strip()
        if query:
            add_pending_search(query)
            self.update_pending_combo()

        QMessageBox.warning(self, "Search Error", f"Failed to search LibGen mirrors:\n{err_msg}")

    # --- Calibre Selection & Hardcover Search Queue Handlers ---
    def update_search_queue_bar(self):
        if not hasattr(self, "search_queue_bar"):
            return
        n_books = len(self.selected_books) if hasattr(self, "selected_books") and self.selected_books else 0
        if n_books > 0:
            if hasattr(self, "queue_info_label"):
                self.queue_info_label.setVisible(False)
            self.start_queue_search_btn.setText(f"📚 Search {n_books} Loaded Calibre Record(s) in Queue (1 match/book)")
            self.start_queue_search_btn.setEnabled(True)
            self.start_queue_search_btn.setVisible(True)
            self.stop_queue_search_btn.setVisible(False)
            self.search_queue_bar.setVisible(True)
        else:
            self.search_queue_bar.setVisible(False)


    def dismiss_search_queue_bar(self):
        self.selected_books = []
        if hasattr(self, "search_queue_bar"):
            self.search_queue_bar.setVisible(False)

    def start_search_queue(self):
        if not self.selected_books:
            return

        if hasattr(self, "search_queue_worker") and self.search_queue_worker and self.search_queue_worker.isRunning():
            return

        self.start_queue_search_btn.setVisible(False)
        if hasattr(self, "pause_queue_search_btn"):
            self.pause_queue_search_btn.setVisible(True)
            self.pause_queue_search_btn.setText("⏸ Pause")
        self.stop_queue_search_btn.setVisible(True)
        self.stop_queue_search_btn.setEnabled(True)
        self.stop_queue_search_btn.setText("Stop Queue Search")
        self.search_btn.setEnabled(False)

        total_recs = len(self.selected_books)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(True)
            self.search_progress_bar.setRange(0, total_recs)
            self.search_progress_bar.setValue(0)
            self.search_progress_bar.setFormat(f"Queue Search: 0/{total_recs} records")

        self.status_label.setText(f"Starting search across {total_recs} record(s)...")
        self.search_mirror_label.setText(f"Parallel search: 0/{total_recs} records processed")
        self.append_log(f"--- Starting Parallel Search Queue ({total_recs} books) ---")

        selected_mirror = self.mirror_combo.currentText().strip()
        if selected_mirror.startswith("Auto"):
            selected_mirror = "Auto"
        mirrors = get_mirrors()

        self.search_queue_worker = SearchQueueWorker(
            records=self.selected_books,
            mirrors=mirrors,
            selected_mirror=selected_mirror,
            timeout=int(prefs.get("timeout", 20)),
            language=self.lang_combo.checked_items(),
            fmt=self.format_combo.currentText().strip(),
            filter_mode=self.filter_combo.currentText().strip(),
            unique_results=self.unique_checkbox.isChecked(),
            parent=self,
        )
        self.search_queue_worker.progress_signal.connect(self.on_search_queue_progress)
        self.search_queue_worker.record_finished_signal.connect(self.on_search_queue_record_finished)
        self.search_queue_worker.finished_signal.connect(self.on_search_queue_finished)
        self.search_queue_worker.start()

    def pause_search_queue(self):
        if hasattr(self, "search_queue_worker") and self.search_queue_worker and self.search_queue_worker.isRunning():
            self.search_queue_worker.abort()
            self.append_log("[Search Queue] Paused search queue. Remaining items preserved.")
            self.status_label.setText("Search queue paused.")
            self.search_mirror_label.setText("Search queue paused.")
            if hasattr(self, "pause_queue_search_btn"):
                self.pause_queue_search_btn.setVisible(False)
            self.stop_queue_search_btn.setVisible(False)
            self.start_queue_search_btn.setVisible(True)
            self.start_queue_search_btn.setEnabled(True)
            self.search_btn.setEnabled(True)

    def stop_search_queue(self):
        if hasattr(self, "search_queue_worker") and self.search_queue_worker and self.search_queue_worker.isRunning():
            self.stop_queue_search_btn.setEnabled(False)
            self.stop_queue_search_btn.setText("Stopping...")
            self.status_label.setText("Stopping search queue...")
            self.search_queue_worker.abort()
        if hasattr(self, "pause_queue_search_btn"):
            self.pause_queue_search_btn.setVisible(False)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

    def on_search_queue_progress(self, idx, total, title, status_msg):
        self.status_label.setText(f"[{idx}/{total}] {status_msg}")
        self.search_mirror_label.setText(f"Batch Search [{idx}/{total}]: {title}")
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(True)
            self.search_progress_bar.setRange(0, total)
            self.search_progress_bar.setValue(idx)
            self.search_progress_bar.setFormat(f"Record {idx}/{total}: {title[:32]}")
        self.append_log(f"[Search Queue] {status_msg}")

    def on_search_queue_record_finished(self, record_info, matched_books):
        added = 0
        for book in matched_books or []:
            if not any(getattr(existing, "detail_url", None) == book.detail_url for existing in self.search_results):
                self.search_results.append(book)
                added += 1
        if added:
            self.populate_results_table()
            count = len(self.search_results)
            self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({count})")
            title = record_info.get("title", "") if isinstance(record_info, dict) else ""
            self.search_mirror_label.setText(f"Added {added} live result(s): {title[:48]}")

    def on_search_queue_finished(self, all_results, matched_cnt, failed_cnt):
        self.start_queue_search_btn.setVisible(True)
        self.start_queue_search_btn.setEnabled(True)
        if hasattr(self, "pause_queue_search_btn"):
            self.pause_queue_search_btn.setVisible(False)
        self.stop_queue_search_btn.setVisible(False)
        self.search_btn.setEnabled(True)
        if hasattr(self, "search_progress_bar"):
            self.search_progress_bar.setVisible(False)

        self.search_results = all_results
        self.populate_results_table()
        # Highlight/select all rows so user can easily review and click 'Add to Queue' or deselect
        self.results_table.selectAll()

        msg = f"✓ Found {len(all_results)} match(es) across {matched_cnt} of {len(self.selected_books)} record(s)."
        if failed_cnt > 0:
            msg += f" ({failed_cnt} with 0 matches added to Pending)"
        self.status_label.setText(msg)
        self.search_mirror_label.setText(msg)
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(all_results)})")
        self.set_current_tab_widget(getattr(self, "tab_results", None))

        self.append_log(f"--- Parallel Search Complete: {len(all_results)} match(es) ready for review in Search Results ---")
        self.append_log("Select desired books in Search Results and click 'Add to Queue' (Ctrl+Shift+A).")

        QMessageBox.information(
            self,
            "Parallel Search Complete",
            f"Parallel search finished!\n\n"
            f"• Records searched: {len(self.selected_books)}\n"
            f"• Matched records: {matched_cnt}\n"
            f"• Total artifacts found: {len(all_results)}\n"
            f"• Zero matches: {failed_cnt}\n\n"
            "All found books have been loaded into Search Results table.\n"
            "Select the books you want and click 'Add to Queue' to queue them for download."
        )

    def populate_results_table(self):
        books = self.search_results
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(books))
        for row, book in enumerate(books):
            title_item = QTableWidgetItem(book.title)
            title_item.setData(Qt.ItemDataRole.UserRole, row)  # Store original index
            if hasattr(book, "calibre_source") and book.calibre_source:
                title_item.setToolTip(f"Matched from Calibre: {book.calibre_source}")
            self.results_table.setItem(row, 0, title_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(book.author))
            pub_year = f"{book.publisher} ({book.year})".strip(" ()")
            self.results_table.setItem(row, 2, QTableWidgetItem(pub_year))
            self.results_table.setItem(row, 3, QTableWidgetItem(book.language))
            self.results_table.setItem(row, 4, QTableWidgetItem(book.extension))
            self.results_table.setItem(row, 5, SizeTableWidgetItem(book.size))
        self.results_table.setSortingEnabled(True)
        self.filter_results_table()

    def filter_results_table(self):
        if not hasattr(self, "results_table") or not hasattr(self, "format_combo"):
            return
        selected_fmt = self.format_combo.currentText().strip().upper()
        for row in range(self.results_table.rowCount()):
            if selected_fmt == "ANY" or not selected_fmt:
                self.results_table.setRowHidden(row, False)
            else:
                item = self.results_table.item(row, 4)
                row_fmt = item.text().strip().upper() if item else ""
                self.results_table.setRowHidden(row, row_fmt != selected_fmt)

    def select_all_results(self):
        self.results_table.selectAll()

    def deselect_all_results(self):
        self.results_table.clearSelection()

    def clear_search_results(self):
        if not self.search_results:
            return
        cnt = len(self.search_results)
        self.search_results.clear()
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), "Search Results (0)")
        self.status_label.setText(f"Cleared {cnt} search result(s).")
        self.append_log(f"[CLEANUP] Cleared {cnt} search result(s).")

    def dedupe_search_results(self):
        if not self.search_results:
            QMessageBox.information(self, "No Search Results", "Search results table is currently empty.")
            return

        initial_cnt = len(self.search_results)
        unique_list = []
        seen_keys = set()

        for book in self.search_results:
            key = None
            if getattr(book, "detail_url", None):
                key = ("url", book.detail_url)
            elif getattr(book, "md5", None):
                key = ("md5", book.md5.lower())
            else:
                norm_title = re.sub(r"\W+", "", (book.title or "").lower())
                norm_author = re.sub(r"\W+", "", (book.author or "").lower())
                key = ("norm", norm_title, norm_author, (book.extension or "").lower())

            if key not in seen_keys:
                seen_keys.add(key)
                unique_list.append(book)

        removed_cnt = initial_cnt - len(unique_list)
        self.search_results = unique_list
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(self.search_results)})")

        msg = f"✓ Removed {removed_cnt} duplicate search result(s). ({len(unique_list)} unique remaining)" if removed_cnt > 0 else "No duplicates found in search results."
        self.status_label.setText(msg)
        self.append_log(f"[CLEANUP] {msg}")
        if hasattr(self, "toast"):
            self.toast.show_toast(msg)

    def dedupe_download_queue(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return

        if not self.queue_manager:
            QMessageBox.information(self, "Empty Queue", "Download queue is currently empty.")
            return

        initial_cnt = len(self.queue_manager)
        unique_queue = []
        seen_keys = set()

        for q in self.queue_manager:
            book = q.get("book")
            if not book:
                continue
            key = None
            if getattr(book, "detail_url", None):
                key = ("url", book.detail_url)
            elif getattr(book, "md5", None):
                key = ("md5", book.md5.lower())
            else:
                norm_title = re.sub(r"\W+", "", (book.title or "").lower())
                norm_author = re.sub(r"\W+", "", (book.author or "").lower())
                key = ("norm", norm_title, norm_author, (book.extension or "").lower())

            if key not in seen_keys:
                seen_keys.add(key)
                unique_queue.append(q)

        removed_cnt = initial_cnt - len(unique_queue)
        self.queue_manager.set_items(unique_queue)

        msg = f"✓ Removed {removed_cnt} duplicate item(s) from Queue. ({len(unique_queue)} remaining)" if removed_cnt > 0 else "No duplicates found in download queue."
        self.status_label.setText(msg)
        self.append_log(f"[CLEANUP] {msg}")
        if hasattr(self, "toast"):
            self.toast.show_toast(msg)

    def discard_selected_results(self):
        selected_rows = set(self.get_selected_result_rows())
        if not selected_rows:
            QMessageBox.information(self, "No Items Selected", "Please select one or more books in the results table.")
            return

        self.search_results = [
            book for idx, book in enumerate(self.search_results)
            if idx not in selected_rows
        ]
        self.populate_results_table()
        self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(self.search_results)})")
        self.status_label.setText(f"Discarded {len(selected_rows)} selected search result(s).")
        self.search_input.setFocus()

    def get_selected_result_rows(self):
        # Extract the original index from UserRole instead of using the sorted row index
        selected_rows = set()
        for idx in self.results_table.selectedIndexes():
            item = self.results_table.item(idx.row(), 0)
            if item is not None:
                orig_idx = item.data(Qt.ItemDataRole.UserRole)
                if orig_idx is not None:
                    selected_rows.add(orig_idx)
        return sorted(list(selected_rows))

    def show_results_context_menu(self, pos):
        selected_rows = self.get_selected_result_rows()
        if not selected_rows:
            return

        menu = QMenu(self)
        count = len(selected_rows)
        add_act = menu.addAction(f"Add Selected ({count}) to Queue\tCtrl+Shift+A")
        add_act.triggered.connect(self.queue_selected_results)
        dl_act = menu.addAction(f"Download Selected ({count})")
        dl_act.triggered.connect(self.download_selected_now)
        discard_act = menu.addAction(f"Discard Selected ({count})")
        discard_act.triggered.connect(self.discard_selected_results)
        menu.exec(self.results_table.viewport().mapToGlobal(pos))

    # --- Queue Handlers ---
    def queue_selected_results(self):
        selected_rows = self.get_selected_result_rows()
        if not selected_rows:
            QMessageBox.information(self, "No Items Selected", "Please select one or more books in the results table.")
            return

        added_count = 0
        queued_urls = set()
        for r in selected_rows:
            if r < len(self.search_results):
                book = self.search_results[r]
                # Avoid duplicates in queue
                if not any(q["book"].detail_url == book.detail_url for q in self.queue_manager):
                    self.queue_manager.append({
                        "book": book,
                        "status": "Queued",
                    })
                    added_count += 1
                queued_urls.add(book.detail_url)

        # Immediately remove queued items from search results
        if queued_urls:
            self.search_results = [b for b in self.search_results if b.detail_url not in queued_urls]
            self.populate_results_table()
            self.set_tab_text_for_widget(getattr(self, "tab_results", None), f"Search Results ({len(self.search_results)})")

        self.update_queue_table()
        if added_count > 0:
            self.status_label.setText(f"Added {added_count} book(s) to Queue.")
        else:
            self.status_label.setText("Selected book(s) already in Queue.")

        # Retain focus directly in the search input
        self.search_input.setFocus()
        self.search_input.selectAll()

    def download_selected_now(self):
        self.queue_selected_results()
        self.start_bulk_download()

    def save_queue(self):
        saved = []
        for q in self.queue_manager:
            bk = q.get("book")
            if bk:
                saved.append({
                    "book": serialize_book(bk),
                    "status": q.get("status", "Queued"),
                    "progress": q.get("progress", 0),
                    "dest_file": q.get("dest_file", ""),
                    "download_timestamp": q.get("download_timestamp", 0),
                })
        prefs["saved_queue_items"] = saved

    def load_queue(self):
        self.queue_manager.clear()
        saved = prefs.get("saved_queue_items", [])
        if not isinstance(saved, list):
            return

        now = time.time()
        retention_days = int(prefs.get("history_retention_days", 30))
        max_downloads = int(prefs.get("max_download_history", 50))
        cutoff = (now - (retention_days * 86400)) if retention_days > 0 else 0

        dl_count = 0
        valid_items = []

        for item in reversed(saved):
            b_dict = item.get("book")
            if not (b_dict and isinstance(b_dict, dict)):
                continue
            status = item.get("status", "Queued")
            is_dl = "downloaded" in status.lower() or "added" in status.lower()
            dl_ts = item.get("download_timestamp", 0)

            if is_dl:
                if cutoff > 0 and dl_ts > 0 and dl_ts < cutoff:
                    continue
                if dl_count >= max_downloads:
                    continue
                dl_count += 1

            valid_items.append({
                "book": deserialize_book(b_dict),
                "status": status,
                "progress": item.get("progress", 0),
                "dest_file": item.get("dest_file", ""),
                "download_timestamp": dl_ts,
            })

        valid_items.reverse()
        self.queue_manager.set_items(valid_items)

    def _set_queue_item_progress(self, row, percent, status_text=None, custom_label=None):
        if row >= self.queue_table.rowCount():
            return
        item = self.queue_table.item(row, 6)
        display_str = custom_label or f"{percent}%"
        if not item:
            item = QTableWidgetItem(display_str)
            self.queue_table.setItem(row, 6, item)
        item.setData(Qt.ItemDataRole.UserRole, int(percent))
        if status_text is not None:
            item.setData(Qt.ItemDataRole.UserRole + 1, str(status_text))
        if custom_label is not None:
            item.setData(Qt.ItemDataRole.UserRole + 2, str(custom_label))
        item.setText(display_str)

    def toggle_activity_log(self, force_open=False):
        if not hasattr(self, "log_view"):
            return
        show = True if force_open else (not self.log_view.isVisible())
        self.log_view.setVisible(show)
        if hasattr(self, "log_toggle_btn"):
            self.log_toggle_btn.setText("▼ Live Activity Log" if show else "▶ Live Activity Log")

    def update_queue_table(self):
        if not hasattr(self, 'queue_table'):
            return
        self.queue_table.setUpdatesEnabled(False)
        try:
            self.queue_table.setRowCount(len(self.queue_manager))
            for row, q in enumerate(self.queue_manager):
                book = q["book"]
                self.queue_table.setItem(row, 0, QTableWidgetItem(book.title))
                self.queue_table.setItem(row, 1, QTableWidgetItem(book.author))
                self.queue_table.setItem(row, 2, QTableWidgetItem(book.extension))
                self.queue_table.setItem(row, 3, QTableWidgetItem(book.size))
                status_text = q.get("status", "Queued")
                status_item = QTableWidgetItem(status_text)
                st_lower = status_text.lower()
                if "failed" in st_lower or "error" in st_lower or "skipped" in st_lower:
                    status_item.setForeground(QColor("#ef4444"))
                elif "downloaded" in st_lower or "added" in st_lower:
                    status_item.setForeground(QColor("#22c55e"))
                self.queue_table.setItem(row, 4, status_item)
                self.queue_table.setItem(row, 5, QTableWidgetItem(""))
                pct = q.get("progress", 0)
                self._set_queue_item_progress(row, pct, status_text)
    
            remaining = sum(
                1 for q in self.queue_manager
                if q.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")
            )
            total = len(self.queue_manager)
            if 0 < remaining < total:
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Downloads ({remaining} left)")
            else:
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Downloads ({total})")
            self._schedule_filter()
            self.save_queue()
        finally:
            self.queue_table.setUpdatesEnabled(True)

    def set_queue_filter(self, mode):
        self.queue_filter_mode = mode
        if hasattr(self, "queue_filter_btns"):
            for m, btn in self.queue_filter_btns.items():
                btn.setChecked(m == mode)
                if m == mode:
                    btn.setStyleSheet(FILTER_BUTTON_ACTIVE_STYLE)
                else:
                    btn.setStyleSheet(FILTER_BUTTON_STYLE)
        self._schedule_filter()

    def _schedule_filter(self):
        if hasattr(self, "_filter_timer") and not self._filter_timer.isActive():
            self._filter_timer.start()

    def apply_queue_filter(self):
        if not hasattr(self, "queue_table") or not hasattr(self, "queue_manager"):
            return

        queued_cnt = 0
        dl_cnt = 0
        downloaded_cnt = 0
        failed_cnt = 0

        for row, q in enumerate(self.queue_manager):
            status = str(q.get("status", "")).lower()
            is_downloaded = "downloaded" in status or "added" in status
            is_failed = (
                "failed" in status
                or "error" in status
                or "skipped" in status
                or "stopped" in status
            ) and not is_downloaded
            is_dl = (
                "downloading" in status
                or "resolving" in status
                or "streaming" in status
                or "piece-together" in status
                or "multi-segment" in status
                or "segment" in status
            ) and not is_downloaded and not is_failed
            is_queued = not is_downloaded and not is_failed and not is_dl

            if is_queued:
                queued_cnt += 1
            elif is_dl:
                dl_cnt += 1
            elif is_downloaded:
                downloaded_cnt += 1
            elif is_failed:
                failed_cnt += 1

            if getattr(self, "queue_filter_mode", "Queued") == "Queued":
                hide = not is_queued
            elif self.queue_filter_mode == "Downloading":
                hide = not is_dl
            elif self.queue_filter_mode == "Downloaded":
                hide = not is_downloaded
            elif self.queue_filter_mode == "Failed":
                hide = not is_failed
            else:
                hide = False

            if row < self.queue_table.rowCount():
                self.queue_table.setRowHidden(row, hide)

        if hasattr(self, "queue_filter_btns"):
            if "Queued" in self.queue_filter_btns:
                self.queue_filter_btns["Queued"].setText(f"Queued ({queued_cnt})")
            if "Downloading" in self.queue_filter_btns:
                self.queue_filter_btns["Downloading"].setText(f"Downloading ({dl_cnt})")
            if "Downloaded" in self.queue_filter_btns:
                self.queue_filter_btns["Downloaded"].setText(f"Downloaded ({downloaded_cnt})")
            if "Failed" in self.queue_filter_btns:
                self.queue_filter_btns["Failed"].setText(f"Failed ({failed_cnt})")

    def clear_downloaded_items(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return
        self.queue_manager.set_items([q for q in self.queue_manager
            if not ("downloaded" in str(q.get("status", "")).lower() or "added" in str(q.get("status", "")).lower())
        ])
        self.update_queue_table()

    def remove_from_queue(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return
        selected_rows = sorted(set(idx.row() for idx in self.queue_table.selectedIndexes()), reverse=True)
        for r in selected_rows:
            del self.queue_manager[r]
        self.update_queue_table()

    def clear_queue(self):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "Please wait or stop the current download before modifying the queue.")
            return
        self.queue_manager.clear()
        self.session_target_indices = []
        if hasattr(self, "bulk_progress_bar"):
            self.bulk_progress_bar.setVisible(False)
        self.update_queue_table()

    # --- Mirrors & Health Handlers ---
    def populate_mirrors_table(self):
        mirrors = get_mirrors()
        primary = prefs.get("primary_mirror", "https://libgen.li").strip().rstrip("/")
        custom = [m.rstrip("/") for m in prefs.get("custom_mirrors", [])]

        self.mirrors_table.setRowCount(0)
        for row, m in enumerate(mirrors):
            self.mirrors_table.insertRow(row)

            # URL
            self.mirrors_table.setItem(row, 0, QTableWidgetItem(m))

            # Health Info: (is_ok, ms, kb_s, speed_str, msg)
            health = self.mirror_health.get(m)
            if health:
                is_ok, ms, kb_s, speed_str, msg = health
                status_item = QTableWidgetItem("Online" if is_ok else "Error")
                status_item.setForeground(QColor("green") if is_ok else QColor("red"))
                latency_item = QTableWidgetItem(f"{ms} ms" if is_ok else "-")
                speed_item = QTableWidgetItem(speed_str if is_ok else "-")
            else:
                saved_latencies = prefs.get("mirror_latencies", {})
                saved_ms = saved_latencies.get(m) if isinstance(saved_latencies, dict) else None
                status_item = QTableWidgetItem("Ready" if saved_ms else "Untested")
                status_item.setForeground(QColor("gray"))
                latency_item = QTableWidgetItem(f"{saved_ms} ms" if saved_ms else "-")
                speed_item = QTableWidgetItem("-")

            self.mirrors_table.setItem(row, 1, status_item)
            self.mirrors_table.setItem(row, 2, latency_item)
            self.mirrors_table.setItem(row, 3, speed_item)

            # Type
            m_type = "Primary" if m == primary else ("Custom" if m in custom else "Fallback")
            type_item = QTableWidgetItem(m_type)
            self.mirrors_table.setItem(row, 4, type_item)

            # Action
            if m in custom:
                del_btn = QPushButton("Remove")
                del_btn.clicked.connect(lambda checked, url=m: self.remove_mirror_handler(url))
                self.mirrors_table.setCellWidget(row, 5, del_btn)
            elif health and not is_ok:
                discard_btn = QPushButton("Discard")
                discard_btn.setStyleSheet(COMPACT_BUTTON_STYLE)
                discard_btn.setToolTip("Discard this dead mirror from your configured mirrors")
                discard_btn.clicked.connect(lambda checked, url=m: self.discard_single_mirror_handler(url))
                self.mirrors_table.setCellWidget(row, 5, discard_btn)
            else:
                self.mirrors_table.setItem(row, 5, QTableWidgetItem("-"))

    def test_all_mirrors(self):
        mirrors = get_mirrors()
        self.test_all_mirrors_btn.setEnabled(False)
        self.status_label.setText("Testing latency and download bandwidth for all LibGen mirrors...")

        self.health_worker = MirrorHealthWorker(mirrors, parent=self)
        self.health_worker.mirrors_discovered.connect(self.on_mirrors_discovered)
        self.health_worker.mirror_tested.connect(self.on_mirror_tested)
        self.health_worker.all_tested.connect(self.on_all_mirrors_tested)
        self.health_worker.start()

    def on_mirrors_discovered(self, live_mirrors):
        fallback_str = prefs.get("fallback_mirrors", "")
        fallbacks = [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip()]
        added = False
        for m in live_mirrors:
            if m not in fallbacks:
                fallbacks.append(m)
                added = True
        
        if added:
            prefs["fallback_mirrors"] = ", ".join(fallbacks)
            self.populate_mirrors_table()

    def on_mirror_tested(self, url, is_ok, ms, kb_s, speed_str, msg):
        self.mirror_health[url] = (is_ok, ms, kb_s, speed_str, msg)
        if is_ok and ms > 0:
            record_mirror_latency(url, ms)
        self.populate_mirrors_table()
        
        host = urlparse(url).netloc or url
        icon = "🟢" if is_ok else "🔴"
        lat_tag = f"📶 {ms}ms" if ms > 0 else ""
        speed_tag = f"⚡ {speed_str}" if (is_ok and speed_str) else ""
        detail = f"{lat_tag} {speed_tag}".strip()
        self.side_mirror_status.appendPlainText(f"{icon} {host} {detail}")

    def on_all_mirrors_tested(self):
        self.test_all_mirrors_btn.setEnabled(True)
        self.update_mirror_combobox()
        self.populate_mirrors_table()
        self.status_label.setText("Mirror speed and latency testing completed. Mirrors sorted by latency.")

    def sort_mirrors_by_speed(self):
        """Sorts mirrors by highest bandwidth and lowest latency."""
        mirrors = get_mirrors()
        if not mirrors:
            return

        def speed_key(m):
            health = self.mirror_health.get(m)
            if not health:
                return (-1.0, -999999)
            is_ok, ms, kb_s, speed_str, msg = health
            if not is_ok:
                return (-1.0, -999999)
            return (kb_s, -ms)

        sorted_mirrors = sorted(mirrors, key=speed_key, reverse=True)
        set_mirror_order(sorted_mirrors)
        self.populate_mirrors_table()
        self.update_mirror_combobox()

        fastest = sorted_mirrors[0]
        health = self.mirror_health.get(fastest)
        if health and health[0]:
            self.status_label.setText(
                f"Sorted by speed! Fastest: {fastest} ({health[3]}, {health[1]} ms)"
            )
        else:
            self.status_label.setText("Mirrors sorted by speed.")

    def set_selected_mirror_primary(self):
        selected_rows = list(set(idx.row() for idx in self.mirrors_table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(self, "Selection Required", "Please select a mirror in the table to set as primary.")
            return

        row = selected_rows[0]
        url = self.mirrors_table.item(row, 0).text().strip()
        prefs["primary_mirror"] = url
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Primary mirror updated to {url}.")

    def add_custom_mirror_handler(self):
        url = self.add_mirror_input.text().strip()
        if not url:
            return

        added_url = add_custom_mirror(url)
        if not added_url:
            QMessageBox.warning(self, "Invalid Mirror", "Please enter a LibGen mirror URL such as https://libgen.me.")
            return
        self.add_mirror_input.clear()
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Added custom mirror: {added_url}")

        # Test new mirror immediately in background
        scraper = LibgenScraper(timeout=8)
        is_ok, ms, kb_s, speed_str, msg = scraper.ping_mirror(added_url, timeout=8)
        self.mirror_health[added_url] = (is_ok, ms, kb_s, speed_str, msg)
        self.populate_mirrors_table()

    def remove_mirror_handler(self, url):
        remove_custom_mirror(url)
        if url in self.mirror_health:
            del self.mirror_health[url]
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Removed mirror: {url}")

    def discard_single_mirror_handler(self, url):
        discard_mirrors([url])
        if url in self.mirror_health:
            del self.mirror_health[url]
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Discarded dead mirror: {url}")
        self.append_log(f"🗑 Discarded dead mirror from configuration: {url}")

    def discard_dead_mirrors(self):
        """Discards all mirrors that failed the health test from the user's mirror list."""
        if not self.mirror_health:
            QMessageBox.information(
                self,
                "Test Required",
                "No health tests have been run yet.\n\nPlease click 'Ping / Test All Mirrors' first to detect dead mirrors."
            )
            return

        dead = [m for m, health in self.mirror_health.items() if health and not health[0]]
        if not dead:
            QMessageBox.information(
                self,
                "No Dead Mirrors",
                "All tested mirrors are currently online! None were discarded."
            )
            return

        dead_list_str = "\n".join(f"• {m}" for m in dead)
        reply = QMessageBox.question(
            self,
            "Discard Dead Mirrors",
            f"The following {len(dead)} mirror(s) failed the health test:\n\n{dead_list_str}\n\n"
            "Discard these dead mirrors from your configured mirrors?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        discard_mirrors(dead)
        for m in dead:
            if m in self.mirror_health:
                del self.mirror_health[m]

        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Discarded {len(dead)} dead mirror(s).")
        self.append_log(f"🗑 Discarded {len(dead)} dead mirror(s) from local configuration.")

    def set_search_query(self, query, field="Author", reset_filters_to_default=True):
        """Pre-fills search query, sets field dropdown to Author, and resets other filters to defaults."""
        self.search_input.setText(query)
        idx = self.field_combo.findText(field)
        if idx >= 0:
            self.field_combo.setCurrentIndex(idx)

        if reset_filters_to_default:
            l_idx = self.lang_combo.findText("Any")
            if l_idx >= 0:
                self.lang_combo.setCurrentIndex(l_idx)

            fmt_idx = self.format_combo.findText("Any")
            if fmt_idx >= 0:
                self.format_combo.setCurrentIndex(fmt_idx)

            m_idx = self.mirror_combo.findText("Auto (Best Latency)")
            if m_idx >= 0:
                self.mirror_combo.setCurrentIndex(m_idx)

            fil_idx = self.filter_combo.findText("Prioritize")
            if fil_idx >= 0:
                self.filter_combo.setCurrentIndex(fil_idx)

            c_idx = self.category_combo.findText("All Categories")
            if c_idx >= 0:
                self.category_combo.setCurrentIndex(c_idx)

        if query:
            self.start_search()


    def append_log(self, text):
        """Appends a timestamped message to the scrolling activity log and auto-scrolls to bottom."""
        if hasattr(self, "log_view") and self.log_view is not None:
            self.log_view.appendPlainText(text)
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def get_download_directory(self):
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "callib")
        raw_dir = prefs.get("download_directory", default_dir) or default_dir
        return os.path.abspath(os.path.expanduser(raw_dir))

    def choose_download_directory(self):
        current_dir = self.get_download_directory()
        selected = QFileDialog.getExistingDirectory(self, "Choose Download Folder", current_dir)
        if selected:
            prefs["download_directory"] = selected
            self.status_label.setText(f"Download folder: {selected}")
            self.save_all_field_preferences()

    def ensure_download_directory(self):
        download_dir = self.get_download_directory()
        try:
            os.makedirs(download_dir, exist_ok=True)
            probe_path = os.path.join(download_dir, ".libgen-write-test")
            with open(probe_path, "w") as f:
                f.write("ok")
            os.remove(probe_path)
        except Exception as e:
            raise Exception(f"Download folder is not writable: {download_dir} ({e})")
        prefs["download_directory"] = download_dir
        return download_dir

    def retry_failed_downloads(self):
        """Finds all failed books in the queue and restarts bulk download with multi-mirror failover."""
        failed_indices = []
        for idx, item in enumerate(self.queue_manager):
            status = item.get("status", "").lower()
            if "fail" in status or status == "failed" or "stop" in status:
                item["status"] = "Queued"
                item["progress"] = 0
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Queued"))
                self.queue_table.setItem(idx, 5, QTableWidgetItem("-"))
                self._set_queue_item_progress(idx, 0, "Queued")
                failed_indices.append(idx)

        if not failed_indices:
            QMessageBox.information(self, "No Failed Downloads", "There are no failed items in the queue to retry.")
            return

        # Explicitly reset the session download counter
        self.session_target_indices = list(failed_indices)
        self.session_total = len(failed_indices)
        self.session_completed = 0
        self.status_label.setText(f"0/{self.session_total} downloaded (Retrying {self.session_total} failed)")

        self.append_log(f"🔄 Retrying {len(failed_indices)} failed book(s), cycling mirrors by best latency...")
        self.start_bulk_download(target_indices=failed_indices)

    def retry_failed_with_bookracy(self):
        """Finds all failed or pending books in the queue and restarts download directly via Bookracy."""
        target_indices = []
        for idx, item in enumerate(self.queue_manager):
            status = item.get("status", "").lower()
            if "fail" in status or status == "failed" or "stop" in status:
                target_indices.append(idx)

        # If no explicit failures found, check for any uncompleted books
        if not target_indices:
            for idx, item in enumerate(self.queue_manager):
                status = item.get("status", "").lower()
                if "downloaded" not in status and "added" not in status:
                    target_indices.append(idx)

        if not target_indices:
            QMessageBox.information(self, "No Items", "There are no pending or failed items in the queue to retry with Bookracy.")
            return

        for idx in target_indices:
            item = self.queue_manager[idx]
            item["force_bookracy"] = True
            item["status"] = "Queued (Bookracy)"
            item["progress"] = 0
            self.queue_table.setItem(idx, 4, QTableWidgetItem("Queued (Bookracy)"))
            self.queue_table.setItem(idx, 5, QTableWidgetItem("-"))
            self._set_queue_item_progress(idx, 0, "Queued (Bookracy)")

        self.session_target_indices = list(target_indices)
        self.session_total = len(target_indices)
        self.session_completed = 0
        self.status_label.setText(f"0/{self.session_total} downloaded (Bookracy Retry)")

        self.append_log(f"⚡ Retrying {len(target_indices)} item(s) directly via Bookracy fallback...")
        self.start_bulk_download(target_indices=target_indices)

    def _toggle_bookracy_fallback(self):
        if hasattr(self, "bookracy_fallback_checkbox"):
            prefs["bookracy_auto_retry_failed"] = self.bookracy_fallback_checkbox.isChecked()
            state_str = "enabled" if self.bookracy_fallback_checkbox.isChecked() else "disabled"
            self.append_log(f"⚡ Bookracy failover retry is now {state_str}.")

    # --- Bulk Download Handlers ---
    def start_bulk_download(self, target_indices=None):
        if hasattr(self, 'download_worker') and self.download_worker and self.download_worker.isRunning():
            QMessageBox.warning(self, "Download in Progress", "A download is already running. Please wait or stop it first.")
            return
        
        import time
        self.bulk_start_time = time.time()

        if target_indices is not None and not isinstance(target_indices, bool):
            self.session_target_indices = list(target_indices)
        else:
            self.session_target_indices = [
                idx for idx, q in enumerate(self.queue_manager) 
                if q.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")
            ]

        if not self.session_target_indices:
            QMessageBox.information(self, "Queue Empty", "No pending books in download queue.")
            return

        self.session_total = len(self.session_target_indices)
        self.session_completed = 0
        remaining = self.session_total

        self.start_download_btn.setVisible(False)
        if hasattr(self, "pause_download_btn"):
            self.pause_download_btn.setVisible(True)
            self.pause_download_btn.setText("⏸ Pause Download")
        self.stop_download_btn.setVisible(True)
        self.stop_download_btn.setEnabled(True)
        self.stop_download_btn.setText("Stop Download")
        self.status_label.setText(f"0/{self.session_total} downloaded ({remaining} remaining)")
        self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)")
        self.append_log(f"--- Starting Bulk Download: {remaining} remaining item(s) ---")

        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(False)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(False)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(False)

        if hasattr(self, "bulk_progress_bar"):
            self.bulk_progress_bar.setVisible(True)
            self.bulk_progress_bar.setMaximum(self.session_total)
            self.bulk_progress_bar.setValue(0)
            self.bulk_progress_bar.setFormat(f"Bulk Download: 0/{self.session_total} books (0%)")

        do_auto_retry = False
        if hasattr(self, 'auto_retry_checkbox'):
            do_auto_retry = self.auto_retry_checkbox.isChecked()

        do_fast_mode = False
        if hasattr(self, 'fast_mode_checkbox'):
            do_fast_mode = self.fast_mode_checkbox.isChecked()

        try:
            download_dir = self.ensure_download_directory()
        except Exception as e:
            QMessageBox.warning(self, "Download Folder Error", str(e))
            self.start_download_btn.setVisible(True)
            self.start_download_btn.setEnabled(True)
            if hasattr(self, "pause_download_btn"):
                self.pause_download_btn.setVisible(False)
            self.stop_download_btn.setVisible(False)
            return

        action = self.download_action_combo.currentText().strip() if hasattr(self, "download_action_combo") else "Import to Calibre"
        prefs["download_action"] = action
        prefs["download_directory"] = download_dir
        self.append_log(f"Saving downloads to: {download_dir}")

        n_conc = 1
        if hasattr(self, "concurrency_spinbox"):
            n_conc = self.concurrency_spinbox.value()
        else:
            n_conc = int(prefs.get("concurrent_downloads", 1))

        self.download_worker = BulkDownloadWorker(
            
            self.queue_manager,
            target_indices=self.session_target_indices,
            auto_retry=do_auto_retry,
            fast_mode=do_fast_mode,
            download_dir=download_dir,
            concurrent_files=n_conc,
            parent=self,
        )

        self.download_worker.item_status.connect(self.on_item_status)
        self.download_worker.item_progress.connect(self.on_item_progress)
        self.download_worker.log_message.connect(self.append_log)
        self.download_worker.link_trying.connect(self.on_link_trying)
        self.download_worker.all_done.connect(self.on_bulk_all_done)
        self.download_worker.start()

    def pause_bulk_download(self):
        if self.download_worker and self.download_worker.isRunning():
            self.append_log("[Downloads] Pausing bulk download. Remaining queued items retained.")
            self.status_label.setText("Downloads paused.")
            self.download_worker.abort()
        if hasattr(self, "pause_download_btn"):
            self.pause_download_btn.setVisible(False)
        self.stop_download_btn.setVisible(False)
        self.start_download_btn.setVisible(True)
        self.start_download_btn.setEnabled(True)
        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(True)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(True)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(True)

    def stop_bulk_download(self):
        if self.download_worker and self.download_worker.isRunning():
            self.stop_download_btn.setEnabled(False)
            self.stop_download_btn.setText("Stopping...")
            self.status_label.setText("Stopping downloads...")
            self.append_log("⚠ Download stop requested by user. Aborting...")
            self.download_worker.abort()
        else:
            self.stop_download_btn.setVisible(False)
            self.stop_download_btn.setText("Stop Download")
            self.stop_download_btn.setEnabled(True)
            self.start_download_btn.setVisible(True)
            self.start_download_btn.setEnabled(True)
        if hasattr(self, "pause_download_btn"):
            self.pause_download_btn.setVisible(False)
        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(True)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(True)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(True)

    def on_link_trying(self, idx, url, stage):
        host = urlparse(url).netloc or url
        if stage == "resolving":
            status_text = f"🔍 Resolving ({host})..."
        elif stage == "segmented":
            status_text = f"🧩 Multi-segment ({host})..."
        else:
            status_text = f"🌊 Streaming ({host})..."

        if idx < len(self.queue_manager):
            self.queue_manager[idx]["status"] = status_text
            self.queue_table.setItem(idx, 4, QTableWidgetItem(status_text))
            self._schedule_filter()
        
        if stage in ("streaming", "segmented"):
            stage_icon = "🧩" if stage == "segmented" else "⚡"
            self.side_mirror_status.appendPlainText(f"{stage_icon} [CDN] {host}")

    def on_item_status(self, idx, status_text):
        if idx < len(self.queue_manager):
            dest_path = ""
            if "|" in status_text:
                status_text, dest_path = status_text.split("|", 1)
                self.queue_manager[idx]["dest_file"] = dest_path

            self.queue_manager[idx]["status"] = status_text
            status_item = QTableWidgetItem(status_text)
            st_lower = status_text.lower()
            if "failed" in st_lower or "error" in st_lower or "skipped" in st_lower:
                status_item.setForeground(QColor("#ef4444"))
                self.toggle_activity_log(force_open=True)
            elif "downloaded" in st_lower or "added" in st_lower:
                status_item.setForeground(QColor("#22c55e"))
                self.queue_manager[idx]["download_timestamp"] = time.time()
                bk = self.queue_manager[idx].get("book")
                dest = dest_path or self.queue_manager[idx].get("dest_file", "")
                if bk:
                    append_download_history(bk, dest)
            self.queue_table.setItem(idx, 4, status_item)
            self._set_queue_item_progress(idx, self.queue_manager[idx].get("progress", 0), status_text)
            self._schedule_filter()
            
            # Active session download counter
            if hasattr(self, "session_target_indices") and self.session_target_indices:
                completed = sum(
                    1 for i in self.session_target_indices 
                    if i < len(self.queue_manager) and self.queue_manager[i].get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"]
                )
                self.session_completed = completed
                total = getattr(self, "session_total", len(self.session_target_indices))
                remaining = max(0, total - completed)
                self.status_label.setText(f"{completed}/{total} downloaded ({remaining} remaining)")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Queue ({remaining} left)" if remaining > 0 else f"Queue ({len(self.queue_manager)})")
                if hasattr(self, "bulk_progress_bar") and total > 0:
                    self.bulk_progress_bar.setVisible(True)
                    self.bulk_progress_bar.setMaximum(total)
                    self.bulk_progress_bar.setValue(completed)
                    pct_tot = int((completed / total) * 100)
                    self.bulk_progress_bar.setFormat(f"Bulk Download: {completed}/{total} books ({pct_tot}%)")
            else:
                downloaded = sum(1 for q in self.queue_manager if q.get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"])
                remaining = max(0, len(self.queue_manager) - downloaded)
                self.status_label.setText(f"{downloaded}/{len(self.queue_manager)} downloaded ({remaining} remaining)")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Downloads ({remaining} left)" if remaining > 0 else f"Downloads ({len(self.queue_manager)})")

    def on_item_progress(self, idx, bytes_read, total_bytes, speed_kb):
        if total_bytes > 0:
            percent = int((bytes_read / total_bytes) * 100)
            read_mb = bytes_read / (1024 * 1024)
            tot_mb = total_bytes / (1024 * 1024)
            rem_bytes = max(0, total_bytes - bytes_read)
            eta_s = int(rem_bytes / (speed_kb * 1024)) if speed_kb > 0 else 0
            eta_str = f" • ETA {eta_s}s" if (0 < eta_s < 3600 and percent < 100) else ""

            # Verbose progress label for the table cell
            cell_label = f"{percent}% ({read_mb:.1f}/{tot_mb:.1f}MB)"

            if idx < len(self.queue_manager):
                self.queue_manager[idx]["progress"] = percent
                self.queue_manager[idx]["speed"] = speed_kb
                speed_str = f"{speed_kb/1024:.1f} MB/s" if speed_kb >= 1024 else f"{speed_kb:.0f} KB/s"
                self.queue_table.setItem(idx, 5, QTableWidgetItem(speed_str + eta_str))
                self._set_queue_item_progress(
                    idx,
                    percent,
                    self.queue_manager[idx].get("status", "Downloading"),
                    custom_label=cell_label,
                )
                speed_icon = "⚡" if speed_kb >= 100 else ("🚀" if speed_kb >= 50 else "📥")
                self.queue_table.setItem(idx, 5, QTableWidgetItem(f"{speed_icon} {speed_kb:.1f} KB/s"))
            
            if hasattr(self, "session_target_indices") and self.session_target_indices:
                completed = sum(
                    1 for i in self.session_target_indices 
                    if i < len(self.queue_manager) and self.queue_manager[i].get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"]
                )
                self.session_completed = completed
                total = getattr(self, "session_total", len(self.session_target_indices))
                remaining = max(0, total - completed)
                self.status_label.setText(f"📥 {completed}/{total} downloaded ({remaining} remaining) • {read_mb:.1f}/{tot_mb:.1f} MB @ {speed_kb:.1f} KB/s{eta_str}")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Downloads ({remaining} left)" if remaining > 0 else f"Downloads ({len(self.queue_manager)})")
                if hasattr(self, "bulk_progress_bar") and total > 0:
                    self.bulk_progress_bar.setVisible(True)
                    self.bulk_progress_bar.setMaximum(total)
                    self.bulk_progress_bar.setValue(completed)
                    pct_tot = int((completed / total) * 100)
                    self.bulk_progress_bar.setFormat(f"📦 Bulk: {completed}/{total} ({pct_tot}%) • ⚡ {speed_kb:.1f} KB/s ({read_mb:.1f}/{tot_mb:.1f} MB){eta_str}")
            else:
                downloaded = sum(1 for q in self.queue_manager if q.get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"])
                remaining = max(0, len(self.queue_manager) - downloaded)
                self.status_label.setText(f"📥 {downloaded}/{len(self.queue_manager)} downloaded ({remaining} remaining) • {read_mb:.1f}/{tot_mb:.1f} MB @ {speed_kb:.1f} KB/s{eta_str}")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Downloads ({remaining} left)" if remaining > 0 else f"Downloads ({len(self.queue_manager)})")
                self.set_tab_text_for_widget(getattr(self, "tab_queue", None), f"Downloads ({remaining} left)" if remaining > 0 else f"Downloads ({len(self.queue_manager)})")

    def import_books_to_library(self, file_paths):
        """Batch import downloaded books into Calibre library."""
        if not file_paths:
            return
        file_paths = [os.path.abspath(os.path.expanduser(p)) for p in file_paths if p and os.path.isfile(p)]
        if not file_paths:
            QMessageBox.warning(self, "Import Failed", "Downloaded files were not readable from the selected folder.")
            return
        try:
            if hasattr(self.gui, "iactions") and "Add Books" in self.gui.iactions:
                add_action = self.gui.iactions["Add Books"]
                if hasattr(add_action, "_add_books"):
                    add_action._add_books(file_paths, False)
                elif hasattr(add_action, "add_books"):
                    add_action.add_books(file_paths)
            else:
                from calibre.gui2.add import Adder
                Adder(file_paths, db=self.gui.current_db, parent=self.gui)
        except Exception as e:
            print(f"[LibGen Plugin] Failed to auto-import books: {e}")

    def on_bulk_all_done(self, downloaded_items, fail_count, is_aborted):
        if hasattr(self, "pause_download_btn"):
            self.pause_download_btn.setVisible(False)
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.setText("Stop Download")
        self.stop_download_btn.setEnabled(True)
        self.start_download_btn.setVisible(True)
        self.start_download_btn.setEnabled(True)

        if hasattr(self, "remove_queue_btn"):
            self.remove_queue_btn.setEnabled(True)
        if hasattr(self, "clear_downloaded_btn"):
            self.clear_downloaded_btn.setEnabled(True)
        if hasattr(self, "clear_queue_btn"):
            self.clear_queue_btn.setEnabled(True)

        import time
        elapsed = 1
        if hasattr(self, 'bulk_start_time') and self.bulk_start_time:
            elapsed = max(1, int(time.time() - self.bulk_start_time))

        if elapsed >= 60:
            time_str = f"{elapsed // 60}m {elapsed % 60}s"
        else:
            time_str = f"{elapsed}s"

        if hasattr(self, "bulk_progress_bar"):
            total = getattr(self, "session_total", len(downloaded_items))
            self.bulk_progress_bar.setMaximum(total if total > 0 else 1)
            self.bulk_progress_bar.setValue(len(downloaded_items))
            self.bulk_progress_bar.setFormat(f"Bulk: {len(downloaded_items)}/{total} completed in {time_str}")

        # Calculate exact total bytes transferred across downloaded items
        total_bytes = 0
        for it in downloaded_items:
            fp = it.get("file_path")
            if fp and os.path.exists(fp):
                try:
                    total_bytes += os.path.getsize(fp)
                except Exception:
                    pass

        # Format transferred data size
        if total_bytes >= 1024 * 1024 * 1024:
            size_str = f"{total_bytes / (1024**3):.2f} GB"
        elif total_bytes >= 1024 * 1024:
            size_str = f"{total_bytes / (1024**2):.2f} MB"
        elif total_bytes >= 1024:
            size_str = f"{total_bytes / 1024:.1f} KB"
        else:
            size_str = f"{total_bytes} B"

        # Calculate average transfer bandwidth
        if total_bytes > 0 and elapsed > 0:
            speed_b = total_bytes / elapsed
            if speed_b >= 1024 * 1024:
                speed_str = f"{speed_b / (1024**2):.2f} MB/s"
            elif speed_b >= 1024:
                speed_str = f"{speed_b / 1024:.1f} KB/s"
            else:
                speed_str = f"{speed_b:.0f} B/s"
        else:
            speed_str = "0 KB/s"

        fastest_cdns = get_fastest_cdns()
        if fastest_cdns:
            medals = ["🏆 1st", "🥈 2nd", "🥉 3rd", "4th", "5th"]
            cdn_ranking_lines = []
            for i, (h, s) in enumerate(fastest_cdns[:5]):
                m_tag = medals[i] if i < len(medals) else f"#{i+1}"
                cdn_ranking_lines.append(f"{m_tag} {h} ({s:.1f} KB/s)")
            self.side_mirror_status.appendPlainText("━━━━━━━━━━━━━━━")
            self.side_mirror_status.appendPlainText("🏆 CDN RANKINGS:")
            for l in cdn_ranking_lines:
                self.side_mirror_status.appendPlainText(f"  {l}")

        cdn_section = ""
        cdn_summary = ""
        if fastest_cdns:
            medals = ["🏆", "🥈", "🥉", "4️⃣", "5️⃣"]
            cdn_lines = "\n".join(
                f"    {medals[i] if i < len(medals) else '•'} {h}: {s:.1f} KB/s"
                for i, (h, s) in enumerate(fastest_cdns[:3])
            )
            cdn_section = f"\n  ⚡ Fastest CDNs:\n{cdn_lines}"
            cdn_summary = "\n\nFastest CDNs:\n" + "\n".join(
                f"{medals[i] if i < len(medals) else '•'} {h}: {s:.1f} KB/s"
                for i, (h, s) in enumerate(fastest_cdns[:3])
            )

        # Formatted statistics banner
        stats_box = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  📊 Bulk Download Statistics\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  ✓ Downloaded:    {len(downloaded_items)} item(s)\n"
            f"  ✗ Failed:        {fail_count} item(s)\n"
            f"  ⏱ Elapsed Time:  {time_str}\n"
            f"  📦 Total Data:    {size_str}\n"
            f"  ⚡ Avg Bandwidth: {speed_str}"
            f"{cdn_section}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        # Always log stats box to Live Log and side mirror status
        self.append_log(stats_box)
        self.side_mirror_status.appendPlainText(f"📊 [SUMMARY] ✓ {len(downloaded_items)} dl • 📦 {size_str} • ⚡ {speed_str} • ⏱ {time_str}")

        stats_summary = {
            "time_str": time_str,
            "size_str": size_str,
            "speed_str": speed_str,
            "fastest_cdns": fastest_cdns,
        }

        summary_dialog_msg = (
            f"Bulk download completed.\n\n"
            f"• Downloaded:     {len(downloaded_items)} book(s)\n"
            f"• Failed:         {fail_count} book(s)\n"
            f"• Elapsed Time:   {time_str}\n"
            f"• Total Data:     {size_str}\n"
            f"• Avg Bandwidth:  {speed_str}"
            f"{cdn_summary}"
        )

        if not downloaded_items:
            if is_aborted:
                self.status_label.setText(f"Aborted ({time_str}): 0 downloaded.")
                if self.show_stats:
                    QMessageBox.information(self, "Download Aborted", f"Downloads were stopped by user.\n\n{summary_dialog_msg}")
            else:
                self.status_label.setText(f"Failed ({time_str}): {fail_count} failed.")
                if self.show_stats:
                    QMessageBox.warning(self, "Download Failed", f"All downloads failed.\n\n{summary_dialog_msg}")
            self._prompt_preserve_failed_items(fail_count)
            return

        self.status_label.setText(f"Completed: {len(downloaded_items)} downloaded ({size_str} @ {speed_str}) in {time_str}")
        if self.show_stats:
            QMessageBox.information(self, "Bulk Download Summary", summary_dialog_msg)

        action = prefs.get("download_action", "Import to Calibre")
        if action == "Save to Folder":
            download_dir = prefs.get("download_directory", self.get_download_directory())
            for it in downloaded_items:
                idx = it["index"]
                self.queue_manager[idx]["status"] = "Downloaded"
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded"))
            self.status_label.setText(f"Saved {len(downloaded_items)} book(s) to {download_dir}.")
            QMessageBox.information(
                self,
                "Download Complete",
                f"Saved {len(downloaded_items)} book(s) to:\n{download_dir}"
            )
            if fail_count > 0:
                self._prompt_preserve_failed_items(fail_count)
            return

        # Present Review modal dialog to user
        review_dlg = ReviewImportDialog(downloaded_items, is_aborted=is_aborted, stats_summary=stats_summary, parent=self)
        if review_dlg.exec() == QDialog.DialogCode.Accepted and review_dlg.approved_items:
            approved = review_dlg.approved_items
            file_paths = [it["file_path"] for it in approved]
            self.import_books_to_library(file_paths)

            approved_indices = set(it["index"] for it in approved)
            for it in downloaded_items:
                idx = it["index"]
                if idx in approved_indices:
                    self.queue_manager[idx]["status"] = "✓ Added to Library"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("✓ Added to Library"))
                else:
                    self.queue_manager[idx]["status"] = "Downloaded (Not Imported)"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded (Not Imported)"))

            self.status_label.setText(f"Successfully added {len(approved)} book(s) to Calibre library.")
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully added {len(approved)} book(s) into your Calibre library."
            )
        else:
            for it in downloaded_items:
                idx = it["index"]
                self.queue_manager[idx]["status"] = "Downloaded (Not Imported)"
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded (Not Imported)"))
            self.status_label.setText("Import skipped. Downloaded books held in queue.")

        if fail_count > 0:
            self._prompt_preserve_failed_items(fail_count)

    def _prompt_preserve_failed_items(self, fail_count):
        if fail_count <= 0:
            return
        reply = QMessageBox.question(
            self,
            "Preserve Failed Downloads?",
            f"{fail_count} download(s) could not complete or were stopped.\n\n"
            "Would you like to dump and preserve the failed downloads and partial chunks in the Queue for later retry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for idx, itm in enumerate(self.queue_manager):
                st = itm.get("status", "").lower()
                if "fail" in st or "stop" in st:
                    itm["status"] = "Queued (Ready to retry)"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("Queued (Ready to retry)"))
            self.set_current_tab_widget(getattr(self, "tab_queue", None))
            self.append_log(f"↻ Preserved {fail_count} failed download(s) and chunks in Queue for later retry.")

    def save_all_field_preferences(self, *args):
        """Starts a debounce timer to persist preferences without spamming disk I/O."""
        if hasattr(self, "save_timer"):
            self.save_timer.start()

    def _do_save_all_field_preferences(self):
        """Actually persists the current values to disk."""
        if hasattr(self, "field_combo"):
            prefs["search_field"] = self.field_combo.currentText().strip()
        if hasattr(self, "category_combo"):
            prefs["search_category"] = self.category_combo.currentText().strip()
        if hasattr(self, "lang_combo"):
            langs = self.lang_combo.checked_items()
            prefs["preferred_languages"] = langs
            prefs["preferred_language"] = ", ".join(langs)
        if hasattr(self, "format_combo"):
            prefs["preferred_format"] = self.format_combo.currentText().strip()
        if hasattr(self, "filter_combo"):
            prefs["filter_mode"] = self.filter_combo.currentText().strip()
        if hasattr(self, "unique_checkbox"):
            prefs["unique_results"] = self.unique_checkbox.isChecked()
        if hasattr(self, "history_checkbox"):
            prefs["save_search_history"] = self.history_checkbox.isChecked()
        if hasattr(self, "fast_mode_checkbox"):
            prefs["fast_mode"] = self.fast_mode_checkbox.isChecked()
        if hasattr(self, "concurrency_spinbox"):
            prefs["concurrent_downloads"] = self.concurrency_spinbox.value()
        if hasattr(self, "download_action_combo"):

            prefs["download_action"] = self.download_action_combo.currentText().strip()
        if hasattr(self, "download_dir_btn"):
            prefs["download_directory"] = self.get_download_directory()
        if hasattr(self, "max_results_spinbox"):
            prefs["max_results"] = self.max_results_spinbox.value()
        if hasattr(self, "mirror_combo"):
            m_text = self.mirror_combo.currentText().strip()
            if m_text.startswith("Auto"):
                m_text = "Auto"
            prefs["selected_mirror"] = m_text
        prefs["dialog_width"] = self.width()
        prefs["dialog_height"] = self.height()
        self.save_queue()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.save_all_field_preferences()

    def closeEvent(self, event):
        # Stop all timers
        for timer_name in ['save_timer', 'neko_timer', 'cover_anim_timer', 'version_click_timer']:
            t = getattr(self, timer_name, None)
            if t:
                t.stop()

        self._do_save_all_field_preferences()
        self.save_header_states()

        # Handle UI confirmation if downloading
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Download Running",
                "Downloads are in progress. Stop downloads and review completed books?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        # Abort and wait all workers
        for worker_attr in ['search_worker', 'search_queue_worker', 
                            'cover_worker', 'health_worker', 
                            'live_mirror_worker', 'download_worker']:
            w = getattr(self, worker_attr, None)
            if w and w.isRunning():
                w.abort()
                w.wait(2000)

        event.accept()
