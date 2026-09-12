#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Dedicated UI dialog for LibGen Downloader with search, field selection,
mirror selection/health checks, and bulk queue download manager directly inside Calibre.
"""

import os
import re
import tempfile
import threading
import concurrent.futures

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
    QMenu,
    QShortcut,
    QKeySequence,
    QPlainTextEdit,
    QTimer,
    QCheckBox,
    QSpinBox,
    QStandardItem,
    QStandardItemModel,
)


from calibre_plugins.libgen_store.config import (
    prefs,
    SUPPORTED_LANGUAGES,
    SUPPORTED_FORMATS,
    FILTER_MODES,
    SEARCH_FIELDS,
    CATEGORIES,
    get_mirrors,
    set_mirror_order,
    add_custom_mirror,
    remove_custom_mirror,
    PLUGIN_VERSION_STR,
    get_fastest_cdns,
)
from calibre_plugins.libgen_store.scraper import LibgenScraper


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

    def update_display_text(self):
        items = self.checked_items()
        if "Any" in items or not items:
            self.setEditText("Lang: Any")
            self.setToolTip("Filter by languages (Click to check multiple)")
        elif len(items) == 1:
            self.setEditText(f"Lang: {items[0]}")
            self.setToolTip(f"Language: {items[0]}")
        else:
            self.setEditText(f"Lang: ({len(items)} selected)")
            self.setToolTip(f"Languages: {', '.join(items)}")

    def hidePopup(self):
        super().hidePopup()
        self.update_display_text()


class SearchWorker(QThread):
    finished_signal = pyqtSignal(list, str)   # books, mirror_used
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, str)  # current_idx, total_mirrors, mirror_url

    def __init__(self, query, search_field, category, selected_mirror, language, fmt, filter_mode, max_results=5, unique_results=True, parent=None):
        super().__init__(parent)
        self.query = query
        self.search_field = search_field
        self.category = category
        self.selected_mirror = selected_mirror
        self.language = language
        self.fmt = fmt
        self.filter_mode = filter_mode
        self.max_results = max_results
        self.unique_results = unique_results
        self._is_aborted = False
        self._current_mirror = ""

    def abort(self):
        self._is_aborted = True

    def run(self):
        try:
            mirrors = get_mirrors()
            timeout = int(prefs.get("timeout", 20))

            scraper = LibgenScraper(mirrors=mirrors, timeout=timeout)

            def on_progress(idx, total, mirror):
                self._current_mirror = mirror
                self.progress_signal.emit(idx, total, mirror)

            books = scraper.search(
                query=self.query,
                search_field=self.search_field,
                category=self.category,
                selected_mirror=self.selected_mirror,
                max_results=self.max_results,
                preferred_language=self.language,
                preferred_format=self.fmt,
                filter_mode=self.filter_mode,
                unique_results=self.unique_results,
                progress_callback=on_progress,
                abort_check=lambda: self._is_aborted,
            )
            if self._is_aborted:
                return
            self.finished_signal.emit(books, self._current_mirror)
        except Exception as e:
            if not self._is_aborted:
                self.error_signal.emit(str(e))


class MirrorHealthWorker(QThread):
    mirror_tested = pyqtSignal(str, bool, int, float, str, str)  # url, is_ok, latency_ms, kb_s, speed_str, status_msg
    all_tested = pyqtSignal()
    mirrors_discovered = pyqtSignal(list)

    def __init__(self, mirrors, parent=None):
        super().__init__(parent)
        self.mirrors = mirrors

    def run(self):
        import concurrent.futures
        scraper = LibgenScraper(timeout=8)
        
        # 1. Fetch live mirrors from open-slum.org
        live_mirrors = scraper.fetch_live_mirrors()
        if live_mirrors:
            self.mirrors_discovered.emit(live_mirrors)
            for m in live_mirrors:
                if m not in self.mirrors:
                    self.mirrors.append(m)

        def _ping(mirror):
            return mirror, scraper.ping_mirror(mirror, timeout=8)
            
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(self.mirrors))) as pool:
            futures = [pool.submit(_ping, m) for m in self.mirrors]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    mirror, (is_ok, ms, kb_s, speed_str, msg) = fut.result()
                    self.mirror_tested.emit(mirror, is_ok, ms, kb_s, speed_str, msg)
                except Exception:
                    pass
        
        self.all_tested.emit()

class CoverFetchWorker(QThread):
    cover_fetched = pyqtSignal(bytes, str)
    cover_failed = pyqtSignal(str)

    def __init__(self, book_or_detail_url, parent=None):
        super().__init__(parent)
        if isinstance(book_or_detail_url, str):
            self.detail_url = book_or_detail_url
            self.book = None
        else:
            self.book = book_or_detail_url
            self.detail_url = getattr(self.book, "detail_url", "")
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def run(self):
        from urllib.parse import urlparse
        try:
            from calibre_plugins.libgen_store.scraper import LibgenScraper
        except Exception:
            try:
                from scraper import LibgenScraper
            except Exception:
                if not self._is_aborted:
                    self.cover_failed.emit(self.detail_url)
                return

        try:
            scraper = LibgenScraper(timeout=5)
            cover_url = getattr(self.book, "cover_url", "") if self.book else ""

            # 1. Resolve cover URL from detail page if not cached
            if not cover_url and self.detail_url:
                if self._is_aborted:
                    return
                _, cover_url = scraper.resolve_details(self.detail_url, timeout=4)

                if not cover_url:
                    fallbacks = scraper.get_fallback_detail_urls(self.detail_url)
                    for fb in fallbacks:
                        if self._is_aborted:
                            return
                        if fb == self.detail_url:
                            continue
                        _, cover_url = scraper.resolve_details(fb, timeout=3)
                        if cover_url:
                            break

                if cover_url and self.book:
                    self.book.cover_url = cover_url

            if self._is_aborted or not cover_url:
                self.cover_failed.emit(self.detail_url)
                return

            # 2. Candidate cover image URLs: libgen.li is primary reliable image host
            img_candidates = []
            parsed = urlparse(cover_url)
            if any(ext in parsed.netloc for ext in [".la", ".gl", ".vg", ".bz"]):
                li_url = cover_url.replace(parsed.netloc, "libgen.li")
                img_candidates.append(li_url)
            if cover_url not in img_candidates:
                img_candidates.append(cover_url)

            b = scraper._get_browser()
            data = None
            for u in img_candidates:
                if self._is_aborted:
                    return
                try:
                    u_parsed = urlparse(u)
                    referer = f"{u_parsed.scheme}://{u_parsed.netloc}/"
                    b.addheaders = [("User-Agent", scraper.USER_AGENT), ("Referer", referer)]
                    resp = b.open(u, timeout=4)
                    chunk = resp.read()
                    if chunk and len(chunk) > 300 and not chunk.startswith(b"<!DOCTYPE") and not chunk.startswith(b"<html"):
                        data = chunk
                        break
                except Exception:
                    continue

            if self._is_aborted:
                return

            if data:
                self.cover_fetched.emit(data, self.detail_url)
                return

            self.cover_failed.emit(self.detail_url)
        except Exception:
            if not self._is_aborted:
                self.cover_failed.emit(self.detail_url)

class LiveMirrorWorker(QThread):
    mirrors_discovered = pyqtSignal(list)
    def run(self):
        try:
            from calibre_plugins.libgen_store.scraper import LibgenScraper
            mirrors = LibgenScraper.fetch_live_mirrors()
            self.mirrors_discovered.emit(mirrors)
        except Exception:
            self.mirrors_discovered.emit([])

class BulkDownloadWorker(QThread):
    item_status = pyqtSignal(int, str)             # index, status text
    item_progress = pyqtSignal(int, int, int, float)  # index, bytes_read, total_bytes, speed_kb
    log_message = pyqtSignal(str)                  # timestamped scrolling log line
    link_trying = pyqtSignal(int, str, str)        # index, url, stage ("resolving" or "streaming")
    all_done = pyqtSignal(list, int, bool)         # downloaded_items, fail_count, is_aborted

    def __init__(self, items, auto_retry=False, fast_mode=False, parent=None):
        super().__init__(parent)
        self.items = items
        self.auto_retry = auto_retry
        self.fast_mode = fast_mode
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def run(self):
        import time
        mirrors = get_mirrors()
        timeout = int(prefs.get("timeout", 20))
        scraper = LibgenScraper(mirrors=mirrors, timeout=timeout)

        temp_dir = tempfile.mkdtemp(prefix="calibre_libgen_")
        downloaded_items = []
        fail_count = 0

        while not self._is_aborted:
            fail_count = 0
            any_processed = False

            pending_items = [(idx, i) for idx, i in enumerate(self.items) if i.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")]
            total_pending = len(pending_items)
            current_num = [0]
            dl_lock = threading.Lock()
            fail_count_ref = [0]

            def process_item(idx, item):
                if self._is_aborted:
                    return

                book = item["book"]
                with dl_lock:
                    current_num[0] += 1
                    c_num = current_num[0]

                ts = time.strftime('%H:%M:%S')
                short_title = (book.title or "Unknown")[:45]
                self.log_message.emit(f"[{ts}] [{c_num}/{total_pending}] Starting: \"{short_title}\"")
                self.item_status.emit(idx, "Resolving mirror link...")

                ext = (book.extension or "epub").lower()
                safe_title = sanitize_filename(book.title or "Unknown")
                safe_author = sanitize_filename(book.author or "Unknown")
                dest_file = os.path.join(temp_dir, f"{safe_title} - {safe_author}.{ext}")

                def on_log(msg):
                    t_now = time.strftime('%H:%M:%S')
                    self.log_message.emit(f"[{t_now}] {msg}")

                def on_progress(bytes_read, total, speed_kb=0.0):
                    self.item_progress.emit(idx, bytes_read, total, float(speed_kb))

                def on_link(url, stage):
                    self.link_trying.emit(idx, url, stage)

                try:
                    self.item_status.emit(idx, "Downloading...")
                    dest_path, cover_url = scraper.resolve_and_download(
                        book.detail_url,
                        dest_file,
                        book_title=book.title,
                        book_author=book.author,
                        book_ext=book.extension,
                        log_callback=on_log,
                        progress_callback=on_progress,
                        link_callback=on_link,
                        abort_check=lambda: self._is_aborted,
                        fast_mode=self.fast_mode,
                    )
                    item["dest_file"] = dest_path
                    item["status"] = "Downloaded"
                    self.item_status.emit(idx, "✓ Downloaded (Pending Review)")
                    with dl_lock:
                        downloaded_items.append({
                            "index": idx,
                            "book": book,
                            "file_path": dest_path,
                        })
                except Exception as e:
                    err_msg = str(e)
                    if "stopped by user" in err_msg.lower() or self._is_aborted:
                        if os.path.exists(dest_file):
                            try:
                                os.remove(dest_file)
                            except Exception:
                                pass
                        self.item_status.emit(idx, "Stopped")
                        on_log(f"⚠ Stopped downloading \"{short_title}\" by user request.")
                        return
                    self.item_status.emit(idx, f"Failed: {err_msg[:40]}")
                    on_log(f"✗ Failed to download \"{short_title}\": {err_msg}")
                    with dl_lock:
                        fail_count_ref[0] += 1

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(process_item, idx, item) for idx, item in pending_items]
                for fut in concurrent.futures.as_completed(futures):
                    pass
            
            fail_count = fail_count_ref[0]

            if not self.auto_retry or fail_count == 0 or self._is_aborted:
                break
            
            if self.auto_retry and fail_count > 0:
                t_now = time.strftime('%H:%M:%S')
                self.log_message.emit(f"[{t_now}] ↻ Auto-retry enabled. Retrying {fail_count} failed item(s) in 3 seconds...")
                for _ in range(30):
                    if self._is_aborted:
                        break
                    time.sleep(0.1)

        self.all_done.emit(downloaded_items, fail_count, bool(self._is_aborted))


class ReviewImportDialog(QDialog):
    """Review modal presented after download completion or abortion to select books for Calibre import."""

    def __init__(self, downloaded_items, is_aborted=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Downloaded Books for Import")
        self.resize(760, 420)
        self.downloaded_items = downloaded_items
        self.is_aborted = is_aborted
        self.approved_items = []

        layout = QVBoxLayout(self)

        status_prefix = "<b>Download stopped early.</b> " if is_aborted else "<b>Bulk download finished.</b> "
        info_text = (
            f"{status_prefix}{len(downloaded_items)} book(s) were successfully downloaded.<br>"
            "Review and choose which books to import into your Calibre library:"
        )
        banner = QLabel(info_text, self)
        banner.setWordWrap(True)
        banner.setStyleSheet(
            "padding: 10px 14px; background-color: #2b3d4f; color: white; border-radius: 4px; font-size: 13px;"
        )
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
        import_all_btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 6px 14px;")
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


class LibgenDialog(QDialog):
    def __init__(self, gui, parent=None):
        super().__init__(parent or gui)
        self.gui = gui
        self.setWindowTitle(f"LibGen Downloader ({PLUGIN_VERSION_STR})")
        self.resize(1020, 620)

        self.search_results = []
        self.queue_items = []
        self.mirror_health = {}
        self.download_worker = None
        self.search_worker = None
        self.health_worker = None
        
        # Debounce timer for saving preferences
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self._do_save_all_field_preferences)

        # In-memory cover cache and text loading animation timer
        self.cover_cache = {}
        self.cover_anim_timer = QTimer(self)
        self.cover_anim_timer.setInterval(110)
        self.cover_anim_timer.timeout.connect(self.update_cover_animation)
        self.cover_anim_frame = 0

        # Hidden download stats toggle (enabled by triple-clicking version badge)
        self.show_stats = bool(prefs.get("show_download_stats", False))
        self.version_click_count = 0
        self.version_click_timer = QTimer(self)
        self.version_click_timer.setInterval(1200)
        self.version_click_timer.setSingleShot(True)
        self.version_click_timer.timeout.connect(self._reset_version_clicks)

        self._setup_ui()
        self.populate_mirrors_table()

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
        self.cover_label.setFixedSize(200, 300)
        self.cover_label.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444; color: #888;")
        self.cover_label.setScaledContents(False)
        right_layout.addWidget(self.cover_label)

        right_layout.addWidget(QLabel("<b>Live Mirror Status</b>"))
        self.side_mirror_status = QPlainTextEdit(self)
        self.side_mirror_status.setReadOnly(True)
        self.side_mirror_status.setFixedWidth(200)
        self.side_mirror_status.setStyleSheet("background-color: #1e1e1e; color: #a5d6ff; font-family: monospace; font-size: 11px;")
        right_layout.addWidget(self.side_mirror_status)
        base_layout.addWidget(right_widget, stretch=1)

        # Top Bar: Search Query, Field, Language, Format, and Mirror Selectors
        top_panel = QVBoxLayout()
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()

        # --- Row 1 ---
        row1.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit(self)
        cur_query = prefs.get("last_search_query", "")
        if cur_query:
            self.search_input.setText(cur_query)
        self.search_input.returnPressed.connect(self.start_search)
        self.search_input.textChanged.connect(self.save_all_field_preferences)
        row1.addWidget(self.search_input, stretch=3)

        row1.addWidget(QLabel("Field:"))
        self.field_combo = QComboBox(self)
        self.field_combo.addItems(list(SEARCH_FIELDS.keys()))
        cur_field = prefs.get("search_field", "All Fields")
        f_idx = self.field_combo.findText(cur_field)
        if f_idx >= 0:
            self.field_combo.setCurrentIndex(f_idx)
        self.field_combo.currentTextChanged.connect(self.save_all_field_preferences)
        row1.addWidget(self.field_combo)

        row1.addWidget(QLabel("Cat:"))
        self.category_combo = QComboBox(self)
        self.category_combo.addItems(list(CATEGORIES.keys()))
        cur_cat = prefs.get("search_category", "All Categories")
        c_idx = self.category_combo.findText(cur_cat)
        if c_idx >= 0:
            self.category_combo.setCurrentIndex(c_idx)
        self.category_combo.currentTextChanged.connect(self.save_all_field_preferences)
        row1.addWidget(self.category_combo)

        self.search_btn = QPushButton("Search", self)
        self.search_btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 5px 12px;")
        self.search_btn.clicked.connect(self.start_search)
        row1.addWidget(self.search_btn)

        self.stop_search_btn = QPushButton("Stop Search", self)
        self.stop_search_btn.setStyleSheet("font-weight: bold; background-color: #8c2a2a; color: white; padding: 5px 12px;")
        self.stop_search_btn.setVisible(False)
        self.stop_search_btn.clicked.connect(self.stop_search)
        row1.addWidget(self.stop_search_btn)

        # --- Row 2 ---
        row2.addWidget(QLabel("Lang:"))
        self.lang_combo = CheckableComboBox(self)
        saved_langs = prefs.get("preferred_languages")
        if not saved_langs:
            single = prefs.get("preferred_language", "English")
            saved_langs = [single] if single else ["English"]
        self.lang_combo.add_checkable_items(SUPPORTED_LANGUAGES, saved_langs)
        self.lang_combo.selection_changed.connect(self.save_all_field_preferences)
        row2.addWidget(self.lang_combo)

        row2.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(SUPPORTED_FORMATS)
        cur_fmt = prefs.get("preferred_format", "Any").upper()
        fmt_idx = self.format_combo.findText(cur_fmt)
        if fmt_idx >= 0:
            self.format_combo.setCurrentIndex(fmt_idx)
        self.format_combo.currentTextChanged.connect(self.save_all_field_preferences)
        row2.addWidget(self.format_combo)

        row2.addWidget(QLabel("Mirror:"))
        self.mirror_combo = QComboBox(self)
        self.update_mirror_combobox()
        self.mirror_combo.currentTextChanged.connect(self.save_all_field_preferences)
        row2.addWidget(self.mirror_combo)

        self.fetch_mirrors_btn = QPushButton("Fetch Live")
        self.fetch_mirrors_btn.setToolTip("Fetch active mirrors from open-slum.org")
        self.fetch_mirrors_btn.clicked.connect(self.manual_fetch_mirrors)
        row2.addWidget(self.fetch_mirrors_btn)

        self.filter_combo = QComboBox(self)
        self.filter_combo.addItems(FILTER_MODES)
        cur_mode = prefs.get("filter_mode", "Prioritize")
        m_idx = self.filter_combo.findText(cur_mode)
        if m_idx >= 0:
            self.filter_combo.setCurrentIndex(m_idx)
        self.filter_combo.currentTextChanged.connect(self.save_all_field_preferences)
        row2.addWidget(self.filter_combo)

        row2.addWidget(QLabel("Max:"))
        self.max_results_spinbox = QSpinBox(self)
        self.max_results_spinbox.setRange(1, 1000)
        self.max_results_spinbox.setValue(5)
        row2.addWidget(self.max_results_spinbox)

        self.unique_checkbox = QCheckBox("Unique", self)
        self.unique_checkbox.setToolTip("Filter out duplicate books (same title, author, and format)")
        self.unique_checkbox.setChecked(bool(prefs.get("unique_results", True)))
        self.unique_checkbox.stateChanged.connect(self.save_all_field_preferences)
        row2.addWidget(self.unique_checkbox)
        
        row2.addStretch(1)

        top_panel.addLayout(row1)
        top_panel.addLayout(row2)
        main_layout.addLayout(top_panel)

        # Tabs: Search Results, Bulk Queue, and Mirrors/Health
        self.tabs = QTabWidget(self)
        self.tabs.currentChanged.connect(self.on_table_selection_changed)

        # --- Tab 1: Search Results ---
        tab_results = QWidget()
        results_layout = QVBoxLayout(tab_results)

        # Inline Search Progress & Active Mirror Display
        search_status_box = QHBoxLayout()
        self.search_mirror_label = QLabel("Search status: Ready", self)
        self.search_mirror_label.setStyleSheet("font-weight: bold; color: #2b5b84;")
        search_status_box.addWidget(self.search_mirror_label, stretch=2)


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

        # Global shortcut: Ctrl+Shift+A to add selected to bulk queue
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

        # Queue Segmentation: All, Queued, Downloading, Failed
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("View:"))
        self.queue_filter_mode = "All"
        self.queue_filter_btns = {}

        for mode in ("All", "Queued", "Downloading", "Failed"):
            btn = QPushButton(f"{mode} (0)", self)
            btn.setCheckable(True)
            if mode == "All":
                btn.setChecked(True)
                btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 3px 10px;")
            else:
                btn.setStyleSheet("padding: 3px 10px;")
            btn.clicked.connect(lambda checked, m=mode: self.set_queue_filter(m))
            filter_bar.addWidget(btn)
            self.queue_filter_btns[mode] = btn

        filter_bar.addStretch(1)
        queue_layout.addLayout(filter_bar)

        self.queue_table = QTableWidget(self)
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels([
            "Title", "Author", "Format", "Size", "Status", "Speed", "Progress"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        queue_layout.addWidget(self.queue_table)

        # Scrolling Live Activity Log
        queue_layout.addWidget(QLabel("Live Download & Mirror Failover Activity:"))
        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        self.log_view.setFixedHeight(120)
        self.log_view.setStyleSheet(
            "background-color: #181818; color: #4af626; font-family: monospace; font-size: 11px; padding: 6px; border: 1px solid #333; border-radius: 4px;"
        )
        self.log_view.setPlaceholderText("Live download events, mirror failovers, and streaming chunks will appear here...")
        queue_layout.addWidget(self.log_view)

        # Queue Bottom Buttons
        queue_btn_bar = QHBoxLayout()
        self.remove_queue_btn = QPushButton("Remove Selected", self)
        self.remove_queue_btn.clicked.connect(self.remove_from_queue)
        queue_btn_bar.addWidget(self.remove_queue_btn)

        self.clear_queue_btn = QPushButton("Clear Queue", self)
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        queue_btn_bar.addWidget(self.clear_queue_btn)

        self.retry_failed_btn = QPushButton("Retry Failed", self)
        self.retry_failed_btn.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.retry_failed_btn.clicked.connect(self.retry_failed_downloads)
        queue_btn_bar.addWidget(self.retry_failed_btn)

        self.auto_retry_checkbox = QCheckBox("Retry until all articles are downloaded", self)
        self.auto_retry_checkbox.setChecked(False)
        queue_btn_bar.addWidget(self.auto_retry_checkbox)

        self.fast_mode_checkbox = QCheckBox("⚡ Fast Mode", self)
        self.fast_mode_checkbox.setToolTip("Fast Mode: 3s mirror probe, skips dead/troubled downloads immediately to Failed list")
        self.fast_mode_checkbox.setChecked(bool(prefs.get("fast_mode", False)))
        self.fast_mode_checkbox.stateChanged.connect(self.save_all_field_preferences)
        queue_btn_bar.addWidget(self.fast_mode_checkbox)

        queue_btn_bar.addStretch()

        self.stop_download_btn = QPushButton("Stop Download", self)
        self.stop_download_btn.setStyleSheet("font-weight: bold; background-color: #8c2a2a; color: white; padding: 6px 14px;")
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.clicked.connect(self.stop_bulk_download)
        queue_btn_bar.addWidget(self.stop_download_btn)

        self.start_download_btn = QPushButton("Start Bulk Download", self)
        self.start_download_btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 6px 14px;")
        self.start_download_btn.clicked.connect(lambda: self.start_bulk_download())
        queue_btn_bar.addWidget(self.start_download_btn)

        queue_layout.addLayout(queue_btn_bar)
        self.tabs.addTab(tab_queue, "Bulk Queue (0)")


        # --- Tab 3: Mirrors & Health ---
        tab_mirrors = QWidget()
        mirrors_layout = QVBoxLayout(tab_mirrors)

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



        # ASCII Cat (Neko) Animation Label
        self.neko_label = QLabel("(=^.^=)zZ", self)
        self.neko_label.setFixedWidth(85)
        self.neko_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.neko_label.setStyleSheet("font-family: monospace; font-weight: bold; font-size: 13px; color: #d35400;")
        status_bar.addWidget(self.neko_label)

        self.neko_timer = QTimer(self)
        self.neko_timer.timeout.connect(self.update_neko_animation)
        self.neko_frame_idx = 0
        self.neko_timer.start(400)

        # Version Badge in Status Bar (Click 3x to toggle hidden download stats)
        self.version_badge = QLabel(PLUGIN_VERSION_STR, self)
        self.version_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_badge.mousePressEvent = self.on_version_badge_clicked
        self._update_version_badge_style()
        status_bar.addWidget(self.version_badge)

        main_layout.addLayout(status_bar)

    def _reset_version_clicks(self):
        self.version_click_count = 0

    def on_version_badge_clicked(self, event):
        self.version_click_count += 1
        self.version_click_timer.start()
        if self.version_click_count >= 3:
            self.version_click_count = 0
            self.version_click_timer.stop()
            self.show_stats = not self.show_stats
            prefs["show_download_stats"] = self.show_stats
            self._update_version_badge_style()
            status_msg = "enabled" if self.show_stats else "disabled"
            self.status_label.setText(f"Download statistics {status_msg}.")
            self.append_log(f"[CONFIG] Download statistics {status_msg} (toggled via version badge).")

    def _update_version_badge_style(self):
        if not hasattr(self, "version_badge"):
            return
        if self.show_stats:
            self.version_badge.setStyleSheet(
                "color: #4ade80; font-size: 11px; padding: 2px 6px; background-color: #1a2e1f; border: 1px solid #22c55e; border-radius: 3px; font-weight: bold;"
            )
            self.version_badge.setToolTip("Download statistics enabled (Click 3x to disable)")
        else:
            self.version_badge.setStyleSheet(
                "color: #888; font-size: 11px; padding: 2px 6px; background-color: #242424; border: 1px solid #3d3d3d; border-radius: 3px;"
            )
            self.version_badge.setToolTip("Version info (Click 3x to toggle download statistics)")

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
        self.mirror_combo.addItem("Auto (Failover)")
        for m in get_mirrors():
            self.mirror_combo.addItem(m)

        cur_selected = prefs.get("selected_mirror", "Auto")
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
                if row < len(self.queue_items):
                    book = self.queue_items[row]["book"]
        
        if book and getattr(book, "detail_url", None):
            cache_key = book.detail_url or book.title
            if cache_key in self.cover_cache:
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
            self.cover_label.setText('<div align="center" style="font-family: sans-serif;"><div style="font-size: 28px; margin-bottom: 6px; color: #444;">📚</div><div style="font-size: 12px; color: #666;">Select a book to preview</div></div>')
            self.cover_label.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")

    def update_cover_animation(self):
        spinners = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        dots = [".  ", ".. ", "...", "   "]
        self.cover_anim_frame = getattr(self, 'cover_anim_frame', 0) + 1
        spin = spinners[self.cover_anim_frame % len(spinners)]
        dot = dots[(self.cover_anim_frame // 2) % len(dots)]

        html = f"""
        <div align="center" style="font-family: sans-serif;">
            <div style="font-size: 30px; margin-bottom: 8px;">📖</div>
            <div style="font-size: 13px; font-weight: bold; color: #a5d6ff;">Loading Cover{dot}</div>
            <div style="font-size: 18px; color: #e67e22; margin-top: 10px; font-family: monospace;">{spin}</div>
        </div>
        """
        self.cover_label.setText(html)
        self.cover_label.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")

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
            self.cover_label.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")
        else:
            self.on_cover_failed("")

    def on_cover_fetched(self, data, detail_url):
        if detail_url:
            self.cover_cache[detail_url] = data

        # Check if the fetched cover still matches the currently selected book
        idx = self.tabs.currentIndex()
        curr_book = None
        if idx == 0:
            rows = self.get_selected_result_rows()
            if rows:
                curr_book = self.search_results[rows[0]]
        elif idx == 1:
            rows = sorted([item.row() for item in self.queue_table.selectedItems()])
            if rows and rows[0] < len(self.queue_items):
                curr_book = self.queue_items[rows[0]]["book"]

        curr_url = getattr(curr_book, "detail_url", "")
        if curr_url == detail_url or not curr_url:
            self.cover_anim_timer.stop()
            self._display_cover_pixmap(data)

    def on_cover_failed(self, detail_url=""):
        self.cover_anim_timer.stop()
        self.cover_label.clear()
        self.cover_label.setText('<div align="center" style="font-family: sans-serif;"><div style="font-size: 26px; margin-bottom: 6px; color: #555;">📁</div><div style="font-size: 12px; color: #777;">No Cover Available</div></div>')
        self.cover_label.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")

    # --- Search Handlers ---
    def start_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        self.search_btn.setVisible(False)
        self.stop_search_btn.setVisible(True)
        self.stop_search_btn.setEnabled(True)
        self.stop_search_btn.setText("Stop Search")



        self.status_label.setText(f"Searching LibGen for '{query}'...")
        self.search_mirror_label.setText(f"Connecting to LibGen mirrors for '{query}'...")

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
        self.stop_search_btn.setVisible(False)
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)

    def on_search_progress(self, idx, total, mirror):
        from urllib.parse import urlparse
        host = urlparse(mirror).netloc or mirror
        percent = int(((idx - 1) / total) * 100) if total > 0 else 0
        fmt_text = f"Mirror {idx}/{total} ({percent}%)"



        msg = f"Querying mirror [{idx}/{total}]: {host} ({mirror})"
        self.status_label.setText(msg)
        self.status_label.setToolTip(mirror)
        self.search_mirror_label.setText(msg)

    def on_search_finished(self, books, mirror_used=""):
        self.search_results = books
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)
        self.stop_search_btn.setVisible(False)


        from urllib.parse import urlparse
        host = urlparse(mirror_used).netloc if mirror_used else "mirror"
        success_text = f"✓ Found {len(books)} books via {host}." if mirror_used else f"✓ Found {len(books)} books."
        self.status_label.setText(success_text)
        self.search_mirror_label.setText(success_text)
        self.tabs.setTabText(0, f"Search Results ({len(books)})")
        self.tabs.setCurrentIndex(0)
        self.populate_results_table()

    def on_search_error(self, err_msg):
        self.search_btn.setVisible(True)
        self.search_btn.setEnabled(True)
        self.stop_search_btn.setVisible(False)


        self.status_label.setText(f"Search failed: {err_msg}")
        self.search_mirror_label.setText(f"Search failed: {err_msg}")
        QMessageBox.warning(self, "Search Error", f"Failed to search LibGen mirrors:\n{err_msg}")

    def populate_results_table(self):
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)
        for row, book in enumerate(self.search_results):
            self.results_table.insertRow(row)
            title_item = QTableWidgetItem(book.title)
            title_item.setData(Qt.ItemDataRole.UserRole, row)  # Store original index
            self.results_table.setItem(row, 0, title_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(book.author))
            pub_year = f"{book.publisher} ({book.year})".strip(" ()")
            self.results_table.setItem(row, 2, QTableWidgetItem(pub_year))
            self.results_table.setItem(row, 3, QTableWidgetItem(book.language))
            self.results_table.setItem(row, 4, QTableWidgetItem(book.extension))
            self.results_table.setItem(row, 5, SizeTableWidgetItem(book.size))
        self.results_table.setSortingEnabled(True)

    def select_all_results(self):
        self.results_table.selectAll()

    def deselect_all_results(self):
        self.results_table.clearSelection()

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
        add_act = menu.addAction(f"Add Selected ({count}) to Bulk Queue\tCtrl+Shift+A")
        add_act.triggered.connect(self.queue_selected_results)
        dl_act = menu.addAction(f"Download Selected ({count}) Now")
        dl_act.triggered.connect(self.download_selected_now)
        menu.exec(self.results_table.viewport().mapToGlobal(pos))

    # --- Queue Handlers ---
    def queue_selected_results(self):
        selected_rows = self.get_selected_result_rows()
        if not selected_rows:
            QMessageBox.information(self, "No Items Selected", "Please select one or more books in the results table.")
            return

        added_count = 0
        for r in selected_rows:
            if r < len(self.search_results):
                book = self.search_results[r]
                # Avoid duplicates in queue
                if not any(q["book"].detail_url == book.detail_url for q in self.queue_items):
                    self.queue_items.append({
                        "book": book,
                        "status": "Queued",
                    })
                    added_count += 1

        self.update_queue_table()
        if added_count > 0:
            self.status_label.setText(f"Added {added_count} book(s) to Bulk Queue.")
        else:
            self.status_label.setText("Selected book(s) already in Bulk Queue.")

        # Retain focus directly in the search input
        self.search_input.setFocus()
        self.search_input.selectAll()

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
            filled = pct // 10
            ascii_bar = "█" * filled + "░" * (10 - filled)
            self.queue_table.setItem(row, 6, QTableWidgetItem(f"[{ascii_bar}] {pct}%"))

        self.tabs.setTabText(1, f"Bulk Queue ({len(self.queue_items)})")
        self.apply_queue_filter()

    def set_queue_filter(self, mode):
        self.queue_filter_mode = mode
        if hasattr(self, "queue_filter_btns"):
            for m, btn in self.queue_filter_btns.items():
                btn.setChecked(m == mode)
                if m == mode:
                    btn.setStyleSheet("font-weight: bold; background-color: #2b5b84; color: white; padding: 3px 10px;")
                else:
                    btn.setStyleSheet("padding: 3px 10px;")
        self.apply_queue_filter()

    def apply_queue_filter(self):
        if not hasattr(self, "queue_table") or not hasattr(self, "queue_items"):
            return

        queued_cnt = 0
        dl_cnt = 0
        failed_cnt = 0
        total_cnt = len(self.queue_items)

        for row, q in enumerate(self.queue_items):
            status = str(q.get("status", "")).lower()
            is_queued = "queued" in status
            is_dl = "downloading" in status or "resolving" in status or "streaming" in status or "piece-together" in status
            is_failed = "failed" in status or "error" in status or "skipped" in status

            if is_queued:
                queued_cnt += 1
            elif is_dl:
                dl_cnt += 1
            elif is_failed:
                failed_cnt += 1

            if getattr(self, "queue_filter_mode", "All") == "All":
                hide = False
            elif self.queue_filter_mode == "Queued":
                hide = not is_queued
            elif self.queue_filter_mode == "Downloading":
                hide = not is_dl
            elif self.queue_filter_mode == "Failed":
                hide = not is_failed
            else:
                hide = False

            self.queue_table.setRowHidden(row, hide)

        if hasattr(self, "queue_filter_btns"):
            if "All" in self.queue_filter_btns:
                self.queue_filter_btns["All"].setText(f"All ({total_cnt})")
            if "Queued" in self.queue_filter_btns:
                self.queue_filter_btns["Queued"].setText(f"Queued ({queued_cnt})")
            if "Downloading" in self.queue_filter_btns:
                self.queue_filter_btns["Downloading"].setText(f"Downloading ({dl_cnt})")
            if "Failed" in self.queue_filter_btns:
                self.queue_filter_btns["Failed"].setText(f"Failed ({failed_cnt})")

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

            # Health Info: (is_ok, ms, kb_s, speed_str, msg)
            health = self.mirror_health.get(m)
            if health:
                is_ok, ms, kb_s, speed_str, msg = health
                status_item = QTableWidgetItem("Online" if is_ok else "Error")
                status_item.setForeground(QColor("green") if is_ok else QColor("red"))
                latency_item = QTableWidgetItem(f"{ms} ms" if is_ok else "-")
                speed_item = QTableWidgetItem(speed_str if is_ok else "-")
            else:
                status_item = QTableWidgetItem("Untested")
                status_item.setForeground(QColor("gray"))
                latency_item = QTableWidgetItem("-")
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
        self.populate_mirrors_table()
        
        from urllib.parse import urlparse
        host = urlparse(url).netloc or url
        status = "OK" if is_ok else "FAIL"
        speed = f"{speed_str}" if is_ok else ""
        self.side_mirror_status.appendPlainText(f"[{status}] {host} {speed}")

    def on_all_mirrors_tested(self):
        self.test_all_mirrors_btn.setEnabled(True)
        self.status_label.setText("Mirror speed and latency testing completed.")

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

            m_idx = self.mirror_combo.findText("Auto (Failover)")
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

    def retry_failed_downloads(self):
        """Finds all failed books in the queue and restarts bulk download with multi-mirror failover."""
        failed_indices = []
        for idx, item in enumerate(self.queue_items):
            status = item.get("status", "").lower()
            if "fail" in status or status == "failed" or "stop" in status:
                item["status"] = "Queued"
                item["progress"] = 0
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Queued"))
                self.queue_table.setItem(idx, 5, QTableWidgetItem("-"))
                self.queue_table.setItem(idx, 6, QTableWidgetItem("[░░░░░░░░░░] 0%"))
                failed_indices.append(idx)

        if not failed_indices:
            QMessageBox.information(self, "No Failed Downloads", "There are no failed items in the queue to retry.")
            return

        # Explicitly reset the session download counter
        self.session_target_indices = list(failed_indices)
        self.session_total = len(failed_indices)
        self.session_completed = 0
        self.status_label.setText(f"0/{self.session_total} downloaded (Retrying {self.session_total} failed)")

        self.append_log(f"🔄 Retrying {len(failed_indices)} failed book(s) with multi-mirror failover...")
        self.start_bulk_download(target_indices=failed_indices)

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
                idx for idx, q in enumerate(self.queue_items) 
                if q.get("status") not in ("✓ Added to Library", "Downloaded", "✓ Downloaded (Pending Review)")
            ]

        if not self.session_target_indices:
            QMessageBox.information(self, "Queue Empty", "No pending books in download queue.")
            return

        self.session_total = len(self.session_target_indices)
        self.session_completed = 0

        self.start_download_btn.setVisible(False)
        self.stop_download_btn.setVisible(True)
        self.stop_download_btn.setEnabled(True)
        self.stop_download_btn.setText("Stop Download")
        self.status_label.setText(f"0/{self.session_total} downloaded")
        self.append_log(f"--- Starting Bulk Download: {self.session_total} pending item(s) ---")

        do_auto_retry = False
        if hasattr(self, 'auto_retry_checkbox'):
            do_auto_retry = self.auto_retry_checkbox.isChecked()

        do_fast_mode = False
        if hasattr(self, 'fast_mode_checkbox'):
            do_fast_mode = self.fast_mode_checkbox.isChecked()

        self.download_worker = BulkDownloadWorker(
            self.queue_items, auto_retry=do_auto_retry, fast_mode=do_fast_mode, parent=self
        )
        self.download_worker.item_status.connect(self.on_item_status)
        self.download_worker.item_progress.connect(self.on_item_progress)
        self.download_worker.log_message.connect(self.append_log)
        self.download_worker.link_trying.connect(self.on_link_trying)
        self.download_worker.all_done.connect(self.on_bulk_all_done)
        self.download_worker.start()

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

    def on_link_trying(self, idx, url, stage):
        from urllib.parse import urlparse
        host = urlparse(url).netloc or url
        if stage == "resolving":
            status_text = f"Resolving ({host})..."
        elif stage == "segmented":
            status_text = f"Piece-together ({host})..."
        else:
            status_text = f"Streaming ({host})..."

        if idx < len(self.queue_items):
            self.queue_items[idx]["status"] = status_text
            self.queue_table.setItem(idx, 4, QTableWidgetItem(status_text))
            self.apply_queue_filter()
        
        if stage == "streaming" or stage == "segmented":
            self.side_mirror_status.appendPlainText(f"[CONN] {host}")

    def on_item_status(self, idx, status_text):
        if idx < len(self.queue_items):
            self.queue_items[idx]["status"] = status_text
            status_item = QTableWidgetItem(status_text)
            st_lower = status_text.lower()
            if "failed" in st_lower or "error" in st_lower or "skipped" in st_lower:
                status_item.setForeground(QColor("#ef4444"))
            elif "downloaded" in st_lower or "added" in st_lower:
                status_item.setForeground(QColor("#22c55e"))
            self.queue_table.setItem(idx, 4, status_item)
            self.apply_queue_filter()
            
            # Active session download counter
            if hasattr(self, "session_target_indices") and self.session_target_indices:
                completed = sum(
                    1 for i in self.session_target_indices 
                    if self.queue_items[i].get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"]
                )
                self.session_completed = completed
                total = getattr(self, "session_total", len(self.session_target_indices))
                self.status_label.setText(f"{completed}/{total} downloaded")
            else:
                downloaded = sum(1 for q in self.queue_items if q.get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"])
                self.status_label.setText(f"{downloaded}/{len(self.queue_items)} downloaded")

    def on_item_progress(self, idx, bytes_read, total_bytes, speed_kb):
        if total_bytes > 0:
            percent = int((bytes_read / total_bytes) * 100)
            if idx < len(self.queue_items):
                self.queue_items[idx]["progress"] = percent
                filled = percent // 10
                ascii_bar = "█" * filled + "░" * (10 - filled)
                self.queue_table.setItem(idx, 6, QTableWidgetItem(f"[{ascii_bar}] {percent}%"))
                self.queue_table.setItem(idx, 5, QTableWidgetItem(f"{speed_kb:.1f} KB/s"))
            
            if hasattr(self, "session_target_indices") and self.session_target_indices:
                completed = sum(
                    1 for i in self.session_target_indices 
                    if self.queue_items[i].get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"]
                )
                total = getattr(self, "session_total", len(self.session_target_indices))
                self.status_label.setText(f"{completed}/{total} downloaded")
            else:
                downloaded = sum(1 for q in self.queue_items if q.get("status") in ["Downloaded", "✓ Downloaded (Pending Review)", "✓ Added to Library"])
                self.status_label.setText(f"{downloaded}/{len(self.queue_items)} downloaded")

    def import_books_to_library(self, file_paths):
        """Batch import downloaded books into Calibre library."""
        if not file_paths:
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
        self.stop_download_btn.setVisible(False)
        self.stop_download_btn.setText("Stop Download")
        self.stop_download_btn.setEnabled(True)
        self.start_download_btn.setVisible(True)
        self.start_download_btn.setEnabled(True)

        import time
        elapsed = 1
        if hasattr(self, 'bulk_start_time') and self.bulk_start_time:
            elapsed = max(1, int(time.time() - self.bulk_start_time))

        if elapsed >= 60:
            time_str = f"{elapsed // 60}m {elapsed % 60}s"
        else:
            time_str = f"{elapsed}s"

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
            self.side_mirror_status.appendPlainText("[FASTEST CDNs] " + ", ".join(f"{h} ({s:.1f} KB/s)" for h, s in fastest_cdns[:3]))

        cdn_section = ""
        cdn_summary = ""
        if fastest_cdns:
            cdn_lines = "\n".join(f"    • {h}: {s:.1f} KB/s" for h, s in fastest_cdns[:3])
            cdn_section = f"\n  ⚡ Fastest CDNs:\n{cdn_lines}"
            cdn_summary = "\n\nFastest CDNs:\n" + "\n".join(f"• {h}: {s:.1f} KB/s" for h, s in fastest_cdns[:3])

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
        if self.show_stats:
            self.append_log(stats_box)
            self.side_mirror_status.appendPlainText(f"[STATS] {len(downloaded_items)} dl, {size_str} @ {speed_str} in {time_str}")

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
                if self.show_stats:
                    self.status_label.setText(f"Aborted ({time_str}): 0 downloaded.")
                    QMessageBox.information(self, "Download Aborted", f"Downloads were stopped by user.\n\n{summary_dialog_msg}")
                else:
                    self.status_label.setText("Aborted: 0 downloaded.")
            else:
                if self.show_stats:
                    self.status_label.setText(f"Failed ({time_str}): {fail_count} failed.")
                    QMessageBox.warning(self, "Download Failed", f"All downloads failed.\n\n{summary_dialog_msg}")
                else:
                    self.status_label.setText(f"Failed: {fail_count} failed.")
            return

        if self.show_stats:
            self.status_label.setText(f"Completed: {len(downloaded_items)} downloaded ({size_str} @ {speed_str}) in {time_str}")
            QMessageBox.information(self, "Bulk Download Summary", summary_dialog_msg)
        else:
            self.status_label.setText(f"Completed: {len(downloaded_items)} downloaded.")

        # Present Review modal dialog to user
        review_dlg = ReviewImportDialog(downloaded_items, is_aborted=is_aborted, parent=self)
        if review_dlg.exec() == QDialog.DialogCode.Accepted and review_dlg.approved_items:
            approved = review_dlg.approved_items
            file_paths = [it["file_path"] for it in approved]
            self.import_books_to_library(file_paths)

            approved_indices = set(it["index"] for it in approved)
            for it in downloaded_items:
                idx = it["index"]
                if idx in approved_indices:
                    self.queue_items[idx]["status"] = "✓ Added to Library"
                    self.queue_table.setItem(idx, 4, QTableWidgetItem("✓ Added to Library"))
                else:
                    self.queue_items[idx]["status"] = "Downloaded (Not Imported)"
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
                self.queue_items[idx]["status"] = "Downloaded (Not Imported)"
                self.queue_table.setItem(idx, 4, QTableWidgetItem("Downloaded (Not Imported)"))
            self.status_label.setText("Import skipped. Downloaded books held in queue.")

    def save_all_field_preferences(self, *args):
        """Starts a debounce timer to persist preferences without spamming disk I/O."""
        if hasattr(self, "save_timer"):
            self.save_timer.start()

    def _do_save_all_field_preferences(self):
        """Actually persists the current values to disk."""
        if hasattr(self, "search_input"):
            prefs["last_search_query"] = self.search_input.text().strip()
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
        if hasattr(self, "fast_mode_checkbox"):
            prefs["fast_mode"] = self.fast_mode_checkbox.isChecked()
        if hasattr(self, "mirror_combo"):
            m_text = self.mirror_combo.currentText().strip()
            if m_text.startswith("Auto"):
                m_text = "Auto"
            prefs["selected_mirror"] = m_text

    def closeEvent(self, event):
        self._do_save_all_field_preferences()
        if hasattr(self, "search_worker") and self.search_worker and self.search_worker.isRunning():
            self.search_worker.abort()
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Download Running",
                "Downloads are in progress. Stop downloads and review completed books?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.download_worker.abort()
                self.download_worker.wait(3000)
                event.accept()
            else:
                event.ignore()
                return
        event.accept()

