import os
import re
import csv

from qt.core import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QLabel,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QByteArray,
    QFileDialog,
)

try:
    from calibre_plugins.libgen_store.config import prefs
except ImportError:
    from config import prefs

PRIMARY_BUTTON_STYLE = "font-weight: 600; padding: 5px 14px;"


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
                clean_t = re.split(r'[:(;,]', title)[0].replace('"', '').strip()
                clean_a = re.split(r'[,;&]', author)[0].replace('"', '').strip() if author else ""
                
                if clean_t:
                    if clean_a and new_api.search(f'title:"={clean_t}" and authors:"={clean_a}"'):
                        return True
                    if new_api.search(f'title:"={clean_t}"'):
                        return True
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
        prefs["csv_import_dialog_width"] = self.width()
        prefs["csv_import_dialog_height"] = self.height()
        prefs["hardcover_dialog_width"] = self.width()
        prefs["hardcover_dialog_height"] = self.height()
        try:
            state_hex = bytes(self.books_table.horizontalHeader().saveState().toHex()).decode("ascii")
            prefs["csv_import_table_header"] = state_hex
            prefs["hardcover_books_table_header"] = state_hex
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
