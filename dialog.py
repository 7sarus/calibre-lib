#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Dedicated UI dialog for LibGen Downloader with search, field selection,
mirror selection/health checks, and bulk queue download manager directly inside Calibre.
"""

import os
import re
import tempfile

from qt.core import (
    Qt,
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
)

from calibre_plugins.libgen_store.config import (
    prefs,
    SUPPORTED_LANGUAGES,
    SUPPORTED_FORMATS,
    FILTER_MODES,
    SEARCH_FIELDS,
    get_mirrors,
    add_custom_mirror,
    remove_custom_mirror,
)
from calibre_plugins.libgen_store.scraper import LibgenScraper


def sanitize_filename(name):
    """Clean filename of illegal filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:100]


class SearchWorker(QThread):
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, query, search_field, selected_mirror, language, fmt, filter_mode, parent=None):
        super().__init__(parent)
        self.query = query
        self.search_field = search_field
        self.selected_mirror = selected_mirror
        self.language = language
        self.fmt = fmt
        self.filter_mode = filter_mode

    def run(self):
        try:
            mirrors = get_mirrors()
            timeout = int(prefs.get("timeout", 20))

            scraper = LibgenScraper(mirrors=mirrors, timeout=timeout)
            books = scraper.search(
                query=self.query,
                search_field=self.search_field,
                selected_mirror=self.selected_mirror,
                max_results=int(prefs.get("max_results", 50)),
                preferred_language=self.language,
                preferred_format=self.fmt,
                filter_mode=self.filter_mode,
            )
            self.finished_signal.emit(books)
        except Exception as e:
            self.error_signal.emit(str(e))


class MirrorHealthWorker(QThread):
    mirror_tested = pyqtSignal(str, bool, int, str)  # url, is_ok, latency_ms, status_msg
    all_tested = pyqtSignal()

    def __init__(self, mirrors, parent=None):
        super().__init__(parent)
        self.mirrors = mirrors

    def run(self):
        scraper = LibgenScraper(timeout=8)
        for mirror in self.mirrors:
            is_ok, ms, msg = scraper.ping_mirror(mirror, timeout=8)
            self.mirror_tested.emit(mirror, is_ok, ms, msg)
        self.all_tested.emit()


class BulkDownloadWorker(QThread):
    item_status = pyqtSignal(int, str)             # index, status text
    item_progress = pyqtSignal(int, int, int)       # index, bytes_read, total_bytes
    book_downloaded = pyqtSignal(int, str)         # index, file_path
    all_done = pyqtSignal(int, int)                # success_count, fail_count

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def run(self):
        mirrors = get_mirrors()
        timeout = int(prefs.get("timeout", 20))
        scraper = LibgenScraper(mirrors=mirrors, timeout=timeout)

        temp_dir = tempfile.mkdtemp(prefix="calibre_libgen_")
        success_count = 0
        fail_count = 0

        for idx, item in enumerate(self.items):
            if self._is_aborted:
                break

            book = item["book"]
            if item.get("status") == "Completed":
                continue

            self.item_status.emit(idx, "Resolving download link...")
            download_url, cover_url = scraper.resolve_details(book.detail_url)

            if not download_url:
                self.item_status.emit(idx, "Failed: Mirror link unavailable")
                fail_count += 1
                continue

            # Build destination filename
            ext = (book.extension or "epub").lower()
            safe_title = sanitize_filename(book.title or "Unknown")
            safe_author = sanitize_filename(book.author or "Unknown")
            dest_file = os.path.join(temp_dir, f"{safe_title} - {safe_author}.{ext}")

            self.item_status.emit(idx, "Downloading...")

            def on_progress(bytes_read, total):
                self.item_progress.emit(idx, bytes_read, total)

            try:
                scraper.download_file(download_url, dest_file, progress_callback=on_progress)
                self.item_status.emit(idx, "Adding to Library...")
                self.book_downloaded.emit(idx, dest_file)
                self.item_status.emit(idx, "✓ Added to Library")
                success_count += 1
            except Exception as e:
                self.item_status.emit(idx, f"Download failed: {e}")
                fail_count += 1

        self.all_done.emit(success_count, fail_count)


class LibgenDialog(QDialog):
    def __init__(self, gui, parent=None):
        super().__init__(parent or gui)
        self.gui = gui
        self.setWindowTitle("LibGen Downloader")
        self.resize(1020, 620)

        self.search_results = []
        self.queue_items = []
        self.mirror_health = {}
        self.download_worker = None
        self.search_worker = None
        self.health_worker = None

        self._setup_ui()
        self.populate_mirrors_table()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # Top Bar: Search Query, Field, Language, Format, and Mirror Selectors
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Title, author, series, ISBN...")
        self.search_input.returnPressed.connect(self.start_search)
        top_bar.addWidget(self.search_input, stretch=3)

        # Search Field Selector
        top_bar.addWidget(QLabel("Field:"))
        self.field_combo = QComboBox(self)
        self.field_combo.addItems(list(SEARCH_FIELDS.keys()))
        cur_field = prefs.get("search_field", "All Fields")
        f_idx = self.field_combo.findText(cur_field)
        if f_idx >= 0:
            self.field_combo.setCurrentIndex(f_idx)
        top_bar.addWidget(self.field_combo)

        # Language Selector
        top_bar.addWidget(QLabel("Lang:"))
        self.lang_combo = QComboBox(self)
        self.lang_combo.addItems(SUPPORTED_LANGUAGES)
        cur_lang = prefs.get("preferred_language", "English")
        l_idx = self.lang_combo.findText(cur_lang)
        if l_idx >= 0:
            self.lang_combo.setCurrentIndex(l_idx)
        top_bar.addWidget(self.lang_combo)

        # Format Selector
        top_bar.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(SUPPORTED_FORMATS)
        cur_fmt = prefs.get("preferred_format", "Any").upper()
        fmt_idx = self.format_combo.findText(cur_fmt)
        if fmt_idx >= 0:
            self.format_combo.setCurrentIndex(fmt_idx)
        top_bar.addWidget(self.format_combo)

        # Mirror Selector
        top_bar.addWidget(QLabel("Mirror:"))
        self.mirror_combo = QComboBox(self)
        self.update_mirror_combobox()
        top_bar.addWidget(self.mirror_combo)

        # Filter Mode (Strict vs Prioritize)
        self.filter_combo = QComboBox(self)
        self.filter_combo.addItems(FILTER_MODES)
        cur_mode = prefs.get("filter_mode", "Prioritize")
        m_idx = self.filter_combo.findText(cur_mode)
        if m_idx >= 0:
            self.filter_combo.setCurrentIndex(m_idx)
        top_bar.addWidget(self.filter_combo)

        self.search_btn = QPushButton("Search", self)
        self.search_btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 5px 12px;")
        self.search_btn.clicked.connect(self.start_search)
        top_bar.addWidget(self.search_btn)

        main_layout.addLayout(top_bar)

        # Tabs: Search Results, Bulk Queue, and Mirrors/Health
        self.tabs = QTabWidget(self)

        # --- Tab 1: Search Results ---
        tab_results = QWidget()
        results_layout = QVBoxLayout(tab_results)

        self.results_table = QTableWidget(self)
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels([
            "Select", "Title", "Author", "Publisher / Year", "Language", "Format", "Size"
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        results_layout.addWidget(self.results_table)

        # Results Bottom Buttons
        btn_bar = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All", self)
        self.select_all_btn.clicked.connect(self.select_all_results)
        btn_bar.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All", self)
        self.deselect_all_btn.clicked.connect(self.deselect_all_results)
        btn_bar.addWidget(self.deselect_all_btn)

        btn_bar.addStretch()

        self.queue_selected_btn = QPushButton("Add Selected to Bulk Queue", self)
        self.queue_selected_btn.setStyleSheet("font-weight: bold; padding: 5px 10px;")
        self.queue_selected_btn.clicked.connect(self.queue_selected_results)
        btn_bar.addWidget(self.queue_selected_btn)

        self.download_now_btn = QPushButton("Download Selected Now", self)
        self.download_now_btn.clicked.connect(self.download_selected_now)
        btn_bar.addWidget(self.download_now_btn)

        results_layout.addLayout(btn_bar)
        self.tabs.addTab(tab_results, "Search Results (0)")

        # --- Tab 2: Bulk Download Queue ---
        tab_queue = QWidget()
        queue_layout = QVBoxLayout(tab_queue)

        self.queue_table = QTableWidget(self)
        self.queue_table.setColumnCount(5)
        self.queue_table.setHorizontalHeaderLabels([
            "Title", "Author", "Format", "Size", "Status"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        queue_layout.addWidget(self.queue_table)

        # Queue Bottom Buttons
        queue_btn_bar = QHBoxLayout()
        self.remove_queue_btn = QPushButton("Remove Selected", self)
        self.remove_queue_btn.clicked.connect(self.remove_from_queue)
        queue_btn_bar.addWidget(self.remove_queue_btn)

        self.clear_queue_btn = QPushButton("Clear Queue", self)
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        queue_btn_bar.addWidget(self.clear_queue_btn)

        queue_btn_bar.addStretch()

        self.start_download_btn = QPushButton("Start Bulk Download", self)
        self.start_download_btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 6px 14px;")
        self.start_download_btn.clicked.connect(self.start_bulk_download)
        queue_btn_bar.addWidget(self.start_download_btn)

        queue_layout.addLayout(queue_btn_bar)
        self.tabs.addTab(tab_queue, "Bulk Queue (0)")

        # --- Tab 3: Mirrors & Health ---
        tab_mirrors = QWidget()
        mirrors_layout = QVBoxLayout(tab_mirrors)

        # Mirrors Table
        self.mirrors_table = QTableWidget(self)
        self.mirrors_table.setColumnCount(5)
        self.mirrors_table.setHorizontalHeaderLabels([
            "Mirror URL", "Status", "Response Rate / Latency", "Type", "Action"
        ])
        self.mirrors_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.mirrors_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.mirrors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        mirrors_layout.addWidget(self.mirrors_table)

        # Mirror Controls
        mirror_actions_bar = QHBoxLayout()
        self.test_all_mirrors_btn = QPushButton("Ping / Test All Mirrors", self)
        self.test_all_mirrors_btn.clicked.connect(self.test_all_mirrors)
        mirror_actions_bar.addWidget(self.test_all_mirrors_btn)

        self.set_primary_btn = QPushButton("Set Selected as Primary", self)
        self.set_primary_btn.clicked.connect(self.set_selected_mirror_primary)
        mirror_actions_bar.addWidget(self.set_primary_btn)

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
        self.tabs.addTab(tab_mirrors, "Mirrors & Health")

        main_layout.addWidget(self.tabs)

        # Bottom Progress & Status Bar
        status_bar = QHBoxLayout()
        self.status_label = QLabel("Ready", self)
        status_bar.addWidget(self.status_label, stretch=2)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedWidth(260)
        status_bar.addWidget(self.progress_bar)

        main_layout.addLayout(status_bar)

    def update_mirror_combobox(self):
        self.mirror_combo.clear()
        self.mirror_combo.addItem("Auto (Failover)")
        for m in get_mirrors():
            self.mirror_combo.addItem(m)

        cur_selected = prefs.get("selected_mirror", "Auto")
        idx = self.mirror_combo.findText(cur_selected)
        if idx >= 0:
            self.mirror_combo.setCurrentIndex(idx)

    # --- Search Handlers ---
    def start_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        self.search_btn.setEnabled(False)
        self.status_label.setText(f"Searching LibGen for '{query}'...")
        self.progress_bar.setRange(0, 0)  # Indeterminate spinner

        # Update saved preferences
        field_text = self.field_combo.currentText().strip()
        field_code = SEARCH_FIELDS.get(field_text, "")
        selected_mirror = self.mirror_combo.currentText().strip()
        if selected_mirror.startswith("Auto"):
            selected_mirror = "Auto"

        prefs["search_field"] = field_text
        prefs["selected_mirror"] = selected_mirror
        prefs["preferred_language"] = self.lang_combo.currentText().strip()
        prefs["preferred_format"] = self.format_combo.currentText().strip()
        prefs["filter_mode"] = self.filter_combo.currentText().strip()

        self.search_worker = SearchWorker(
            query=query,
            search_field=field_code,
            selected_mirror=selected_mirror,
            language=self.lang_combo.currentText().strip(),
            fmt=self.format_combo.currentText().strip(),
            filter_mode=self.filter_combo.currentText().strip(),
            parent=self,
        )
        self.search_worker.finished_signal.connect(self.on_search_finished)
        self.search_worker.error_signal.connect(self.on_search_error)
        self.search_worker.start()

    def on_search_finished(self, books):
        self.search_results = books
        self.search_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Found {len(books)} books.")
        self.tabs.setTabText(0, f"Search Results ({len(books)})")
        self.tabs.setCurrentIndex(0)
        self.populate_results_table()

    def on_search_error(self, err_msg):
        self.search_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Search failed: {err_msg}")
        QMessageBox.warning(self, "Search Error", f"Failed to search LibGen mirrors:\n{err_msg}")

    def populate_results_table(self):
        self.results_table.setRowCount(0)
        for row, book in enumerate(self.search_results):
            self.results_table.insertRow(row)

            # Checkbox item
            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb_item.setCheckState(Qt.CheckState.Unchecked)
            self.results_table.setItem(row, 0, cb_item)

            # Text items
            self.results_table.setItem(row, 1, QTableWidgetItem(book.title))
            self.results_table.setItem(row, 2, QTableWidgetItem(book.author))
            pub_year = f"{book.publisher} ({book.year})".strip(" ()")
            self.results_table.setItem(row, 3, QTableWidgetItem(pub_year))
            self.results_table.setItem(row, 4, QTableWidgetItem(book.language))
            self.results_table.setItem(row, 5, QTableWidgetItem(book.extension))
            self.results_table.setItem(row, 6, QTableWidgetItem(book.size))

    def select_all_results(self):
        for r in range(self.results_table.rowCount()):
            item = self.results_table.item(r, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def deselect_all_results(self):
        for r in range(self.results_table.rowCount()):
            item = self.results_table.item(r, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    # --- Queue Handlers ---
    def queue_selected_results(self):
        added_count = 0
        for r in range(self.results_table.rowCount()):
            item = self.results_table.item(r, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                book = self.search_results[r]
                # Avoid duplicates in queue
                if not any(q["book"].detail_url == book.detail_url for q in self.queue_items):
                    self.queue_items.append({
                        "book": book,
                        "status": "Queued",
                    })
                    added_count += 1
                item.setCheckState(Qt.CheckState.Unchecked)

        if added_count > 0:
            self.update_queue_table()
            self.status_label.setText(f"Added {added_count} book(s) to download queue.")
            self.tabs.setCurrentIndex(1)
        else:
            QMessageBox.information(self, "No Items Selected", "Please check at least one book to add to queue.")

    def download_selected_now(self):
        self.queue_selected_results()
        self.start_bulk_download()

    def update_queue_table(self):
        self.queue_table.setRowCount(0)
        for row, q in enumerate(self.queue_items):
            self.queue_table.insertRow(row)
            book = q["book"]
            self.queue_table.setItem(row, 0, QTableWidgetItem(book.title))
            self.queue_table.setItem(row, 1, QTableWidgetItem(book.author))
            self.queue_table.setItem(row, 2, QTableWidgetItem(book.extension))
            self.queue_table.setItem(row, 3, QTableWidgetItem(book.size))
            self.queue_table.setItem(row, 4, QTableWidgetItem(q.get("status", "Queued")))

        self.tabs.setTabText(1, f"Bulk Queue ({len(self.queue_items)})")

    def remove_from_queue(self):
        selected_rows = sorted(set(idx.row() for idx in self.queue_table.selectedIndexes()), reverse=True)
        for r in selected_rows:
            del self.queue_items[r]
        self.update_queue_table()

    def clear_queue(self):
        self.queue_items.clear()
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

            # Health Info
            health = self.mirror_health.get(m)
            if health:
                is_ok, ms, msg = health
                status_item = QTableWidgetItem("Online" if is_ok else "Error")
                status_item.setForeground(QColor("green") if is_ok else QColor("red"))
                rate_item = QTableWidgetItem(msg)
            else:
                status_item = QTableWidgetItem("Untested")
                status_item.setForeground(QColor("gray"))
                rate_item = QTableWidgetItem("-")

            self.mirrors_table.setItem(row, 1, status_item)
            self.mirrors_table.setItem(row, 2, rate_item)

            # Type
            m_type = "Primary" if m == primary else ("Custom" if m in custom else "Fallback")
            type_item = QTableWidgetItem(m_type)
            self.mirrors_table.setItem(row, 3, type_item)

            # Action
            if m in custom:
                del_btn = QPushButton("Remove")
                del_btn.clicked.connect(lambda checked, url=m: self.remove_mirror_handler(url))
                self.mirrors_table.setCellWidget(row, 4, del_btn)
            else:
                self.mirrors_table.setItem(row, 4, QTableWidgetItem("-"))

    def test_all_mirrors(self):
        mirrors = get_mirrors()
        self.test_all_mirrors_btn.setEnabled(False)
        self.status_label.setText("Pinging all LibGen mirrors...")
        self.progress_bar.setRange(0, len(mirrors))
        self.progress_bar.setValue(0)

        self.health_worker = MirrorHealthWorker(mirrors, parent=self)
        self.health_worker.mirror_tested.connect(self.on_mirror_tested)
        self.health_worker.all_tested.connect(self.on_all_mirrors_tested)
        self.health_worker.start()

    def on_mirror_tested(self, url, is_ok, ms, msg):
        self.mirror_health[url] = (is_ok, ms, msg)
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        self.populate_mirrors_table()

    def on_all_mirrors_tested(self):
        self.test_all_mirrors_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText("Mirror health testing completed.")

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
        self.add_mirror_input.clear()
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Added custom mirror: {added_url}")

        # Test new mirror immediately in background
        scraper = LibgenScraper(timeout=8)
        is_ok, ms, msg = scraper.ping_mirror(added_url, timeout=8)
        self.mirror_health[added_url] = (is_ok, ms, msg)
        self.populate_mirrors_table()

    def remove_mirror_handler(self, url):
        remove_custom_mirror(url)
        if url in self.mirror_health:
            del self.mirror_health[url]
        self.populate_mirrors_table()
        self.update_mirror_combobox()
        self.status_label.setText(f"Removed mirror: {url}")

    # --- Bulk Download Handlers ---
    def start_bulk_download(self):
        pending = [q for q in self.queue_items if q.get("status") != "✓ Added to Library"]
        if not pending:
            QMessageBox.information(self, "Queue Empty", "No pending books in download queue.")
            return

        self.start_download_btn.setEnabled(False)
        self.status_label.setText(f"Starting bulk download of {len(pending)} books...")
        self.progress_bar.setValue(0)

        self.download_worker = BulkDownloadWorker(self.queue_items, parent=self)
        self.download_worker.item_status.connect(self.on_item_status)
        self.download_worker.item_progress.connect(self.on_item_progress)
        self.download_worker.book_downloaded.connect(self.on_book_downloaded)
        self.download_worker.all_done.connect(self.on_bulk_all_done)
        self.download_worker.start()

    def on_item_status(self, idx, status_text):
        if idx < len(self.queue_items):
            self.queue_items[idx]["status"] = status_text
            self.queue_table.setItem(idx, 4, QTableWidgetItem(status_text))
            self.status_label.setText(f"[{idx + 1}/{len(self.queue_items)}] {status_text}")

    def on_item_progress(self, idx, bytes_read, total_bytes):
        if total_bytes > 0:
            percent = int((bytes_read / total_bytes) * 100)
            self.progress_bar.setValue(percent)
            book_title = self.queue_items[idx]["book"].title[:30]
            self.status_label.setText(
                f"[{idx + 1}/{len(self.queue_items)}] {book_title}... ({bytes_read // 1024} KB / {total_bytes // 1024} KB)"
            )

    def on_book_downloaded(self, idx, file_path):
        """Directly import downloaded book into Calibre library."""
        try:
            if hasattr(self.gui, "iactions") and "Add Books" in self.gui.iactions:
                add_action = self.gui.iactions["Add Books"]
                if hasattr(add_action, "_add_books"):
                    add_action._add_books([file_path], False)
                elif hasattr(add_action, "add_books"):
                    add_action.add_books([file_path])
            else:
                from calibre.gui2.add import Adder
                Adder([file_path], db=self.gui.current_db, parent=self.gui)
        except Exception as e:
            print(f"[LibGen Plugin] Failed to auto-import {file_path}: {e}")

    def on_bulk_all_done(self, success_count, fail_count):
        self.start_download_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        msg = f"Bulk download completed!\nSuccessfully added to library: {success_count}\nFailed: {fail_count}"
        self.status_label.setText(f"Done: {success_count} added, {fail_count} failed.")
        QMessageBox.information(self, "Download Complete", msg)

    def closeEvent(self, event):
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Download Running",
                "Downloads are currently in progress. Cancel downloads and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.download_worker.abort()
                event.accept()
            else:
                event.ignore()
                return
        event.accept()
