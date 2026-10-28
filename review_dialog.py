from qt.core import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QByteArray,
    Qt,
)

try:
    from calibre_plugins.libgen_store.config import prefs
except ImportError:
    from config import prefs

PRIMARY_BUTTON_STYLE = "font-weight: 600; padding: 5px 14px;"


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
