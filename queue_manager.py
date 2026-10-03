from qt.core import QObject, pyqtSignal
import time

class QueueManager(QObject):
    queue_updated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._items = []

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, idx):
        return self._items[idx]
        
    def __setitem__(self, idx, val):
        self._items[idx] = val
        self.queue_updated.emit()
        
    def __delitem__(self, idx):
        del self._items[idx]
        self.queue_updated.emit()

    def get_items(self):
        return self._items
        
    def set_items(self, items):
        self._items = list(items)
        self.queue_updated.emit()

    def append(self, item):
        self._items.append(item)
        self.queue_updated.emit()

    def extend(self, items):
        self._items.extend(items)
        self.queue_updated.emit()

    def clear(self):
        self._items.clear()
        self.queue_updated.emit()

    def pop(self, idx=-1):
        ret = self._items.pop(idx)
        self.queue_updated.emit()
        return ret
