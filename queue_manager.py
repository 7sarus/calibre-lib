from qt.core import QObject, pyqtSignal
import time

class QueueManager(QObject):
    queue_updated = pyqtSignal()
    item_status_changed = pyqtSignal(int, str)  # idx, status
    item_progress_changed = pyqtSignal(int, int) # idx, progress

    def __init__(self):
        super().__init__()
        self._items = []

    def get_items(self):
        return self._items

    def count(self):
        return len(self._items)

    def add_book(self, book):
        if not any(q["book"].detail_url == book.detail_url for q in self._items):
            self._items.append({
                "book": book,
                "status": "Queued",
                "progress": 0,
                "dest_file": "",
                "download_timestamp": 0
            })
            self.queue_updated.emit()
            return True
        return False

    def remove_at(self, idx):
        if 0 <= idx < len(self._items):
            del self._items[idx]
            self.queue_updated.emit()
            return True
        return False

    def clear(self):
        self._items.clear()
        self.queue_updated.emit()

    def set_status(self, idx, status):
        if 0 <= idx < len(self._items):
            self._items[idx]["status"] = status
            self.item_status_changed.emit(idx, status)
            self.queue_updated.emit()

    def set_progress(self, idx, progress):
        if 0 <= idx < len(self._items):
            self._items[idx]["progress"] = progress
            self.item_progress_changed.emit(idx, progress)
            self.queue_updated.emit()

    def get_status(self, idx):
        if 0 <= idx < len(self._items):
            return self._items[idx].get("status", "")
        return ""
