#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration settings and preferences UI for the LibGen Store plugin.
"""

import os
import re
import time
import json
import threading
from calibre.utils.config import JSONConfig

_prefs_lock = threading.Lock()
from qt.core import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QLabel,
    QGroupBox,
    QCheckBox,
    QPushButton,
    QMessageBox,
)

# Plugin Version definitions
PLUGIN_VERSION = (1, 11, 0, "b")
_BASE_VERSION_STR = "v1.11b"
_BUILD_COMMIT = "74"




def _resolve_version_str():
    try:
        import subprocess

        cmd = ["git", "rev-list", "--count", "HEAD"]
        cnt = (
            subprocess.check_output(cmd, cwd=os.path.dirname(__file__), stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
        if cnt:
            return f"{_BASE_VERSION_STR}-{cnt}"
    except Exception:
        pass
    if _BUILD_COMMIT:
        return f"{_BASE_VERSION_STR}-{_BUILD_COMMIT}"
    return _BASE_VERSION_STR


PLUGIN_VERSION_STR = _resolve_version_str()

# Store configuration under Calibre's standard plugin config path
prefs = JSONConfig("plugins/libgen_store")

PERMANENT_MIRRORS = (
    "https://libgen.li",
    "https://libgen.me",
)
DEFAULT_FALLBACK_MIRRORS = (
    "https://libgen.me",
    "https://libgen.vg",
    "https://libgen.gl",
    "https://libgen.bz",
    "https://libgen.la",
)
_VALID_MIRROR_RE = re.compile(r"^https?://(?:www\.)?libgen\.[a-z]{2,}(?::\d+)?/?$", re.IGNORECASE)


def normalize_mirror_url(url):
    """Returns a canonical LibGen mirror URL, or an empty string for invalid links."""
    clean = (url or "").strip().rstrip("/")
    if not clean:
        return ""
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    if not _VALID_MIRROR_RE.match(clean):
        return ""
    return clean.lower()

# Default preferences
prefs.defaults["primary_mirror"] = "https://libgen.li"
prefs.defaults["fallback_mirrors"] = ", ".join(DEFAULT_FALLBACK_MIRRORS)
prefs.defaults["preferred_language"] = "English"
prefs.defaults["preferred_format"] = "Any"
prefs.defaults["custom_mirrors"] = []
prefs.defaults["selected_mirror"] = "Auto"
prefs.defaults["search_field"] = "All Fields"
prefs.defaults["search_category"] = "All Categories"
prefs.defaults["filter_mode"] = "Prioritize"
prefs.defaults["last_search_query"] = ""
prefs.defaults["last_successful_mirror"] = ""
prefs.defaults["mirror_success_counts"] = {}
prefs.defaults["mirror_latencies"] = {}
prefs.defaults["max_results"] = 5
prefs.defaults["search_timeout"] = 8
prefs.defaults["show_download_stats"] = False
prefs.defaults["show_cats"] = False
prefs.defaults["fastest_cdns"] = {}
prefs.defaults["unique_results"] = True
prefs.defaults["fast_mode"] = False
prefs.defaults["concurrent_downloads"] = 1
prefs.defaults["download_action"] = "Import to Calibre"

prefs.defaults["download_directory"] = os.path.join(os.path.expanduser("~"), "Downloads", "callib")
prefs.defaults["save_search_history"] = False
prefs.defaults["max_search_history"] = 50
prefs.defaults["max_download_history"] = 50
prefs.defaults["history_retention_days"] = 30
prefs.defaults["pending_searches"] = []
prefs.defaults["hardcover_token"] = ""
prefs.defaults["hardcover_match_mode"] = "ISBN Only"
prefs.defaults["hardcover_max_queue_limit"] = 10
prefs.defaults["hardcover_skip_in_library"] = True
prefs.defaults["hardcover_shelves_cache"] = {}
prefs.defaults["hardcover_books_cache"] = {}
prefs.defaults["hardcover_dialog_width"] = 640
prefs.defaults["hardcover_dialog_height"] = 460
prefs.defaults["hardcover_books_table_header"] = ""
prefs.defaults["review_dialog_width"] = 720
prefs.defaults["review_dialog_height"] = 420
prefs.defaults["review_table_header"] = ""
prefs.defaults["cover_panel_width"] = 200
prefs.defaults["cover_panel_height"] = 300
prefs.defaults["log_panel_height"] = 120
prefs.defaults["dialog_width"] = 920
prefs.defaults["dialog_height"] = 600

SEARCH_FIELDS = {
    "All Fields": "",
    "Title": "t",
    "Author": "a",
    "Series": "s",
    "Publisher": "p",
    "Year": "y",
    "ISBN": "i",
}

CATEGORIES = {
    "All Categories": "",
    "Fiction": "f",
    "Sci-Tech / Non-Fiction": "l",
    "Scientific Articles / Papers": "a",
    "Comics": "c",
    "Magazines": "m",
}

def get_mirrors():
    """Returns an ordered list of unique mirrors, defaulting to lowest latency first."""
    primary = normalize_mirror_url(prefs.get("primary_mirror", "https://libgen.li")) or "https://libgen.li"
    fallback_str = prefs.get("fallback_mirrors", "")
    fallbacks = [normalize_mirror_url(m) for m in fallback_str.split(",")]
    custom = [normalize_mirror_url(m) for m in prefs.get("custom_mirrors", [])]
    cleaned_fallbacks = [m for m in fallbacks if m]
    cleaned_custom = [m for m in custom if m]

    if cleaned_fallbacks != [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip()]:
        prefs["fallback_mirrors"] = ", ".join(cleaned_fallbacks)
    if cleaned_custom != prefs.get("custom_mirrors", []):
        prefs["custom_mirrors"] = cleaned_custom

    pool = []
    for m in [primary] + list(PERMANENT_MIRRORS) + cleaned_fallbacks + cleaned_custom:
        if m and m not in pool:
            pool.append(m)

    latencies = prefs.get("mirror_latencies", {})
    if not isinstance(latencies, dict):
        latencies = {}

    def latency_key(url):
        # Lowest positive ms first. Untested mirrors (None / <=0) follow tested ones.
        ms = latencies.get(url)
        if ms is not None and isinstance(ms, (int, float)) and ms > 0:
            return (0, ms)
        return (1, 999999)

    pool.sort(key=latency_key)
    return pool

def record_mirror_latency(mirror_url, latency_ms):
    """Records mirror ping latency in milliseconds, promoting lowest latency mirror to primary."""
    if not mirror_url or latency_ms is None:
        return
    clean = normalize_mirror_url(mirror_url)
    if not clean:
        return
    try:
        ms = int(latency_ms)
    except (ValueError, TypeError):
        return
    with _prefs_lock:
        lats = prefs.get("mirror_latencies", {})
        if not isinstance(lats, dict):
            lats = {}
        if ms > 0:
            lats[clean] = ms
        else:
            lats.pop(clean, None)
        prefs["mirror_latencies"] = lats
        # Best latency becomes primary if valid
        valid_tested = {k: v for k, v in lats.items() if isinstance(v, (int, float)) and v > 0}
        if valid_tested:
            best_mirror = min(valid_tested, key=valid_tested.get)
            if best_mirror in get_mirrors():
                prefs["primary_mirror"] = best_mirror

def record_successful_mirror(mirror_url):
    """Persists mirror success and promotes the most successful mirror to primary."""
    if not mirror_url:
        return
    clean = normalize_mirror_url(mirror_url)
    if clean:
        with _prefs_lock:
            prefs["last_successful_mirror"] = clean
            counts = prefs.get("mirror_success_counts", {})
            if not isinstance(counts, dict):
                counts = {}
            counts[clean] = int(counts.get(clean, 0)) + 1
            prefs["mirror_success_counts"] = dict(
                sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]
            )
            best = max(counts, key=counts.get)
            if best in get_mirrors():
                prefs["primary_mirror"] = best

def add_custom_mirror(url):
    with _prefs_lock:
        url = normalize_mirror_url(url)
        if not url:
            return ""
        custom = list(prefs.get("custom_mirrors", []))
        if url not in custom:
            custom.append(url)
            if len(custom) > 20:
                custom = custom[-20:]
            prefs["custom_mirrors"] = custom
    return url

def remove_custom_mirror(url):
    url = normalize_mirror_url(url)
    custom = [m for m in prefs.get("custom_mirrors", []) if normalize_mirror_url(m) != url]
    prefs["custom_mirrors"] = custom

def discard_mirrors(urls_to_discard):
    """Removes the given URLs from primary, fallback, custom, and last_successful mirrors."""
    discard_set = set(normalize_mirror_url(u) for u in urls_to_discard if u)
    discard_set.discard("")
    discard_set.difference_update(PERMANENT_MIRRORS)
    if not discard_set:
        return

    # 1. Custom mirrors
    custom = [m for m in prefs.get("custom_mirrors", []) if m.rstrip("/") not in discard_set]
    prefs["custom_mirrors"] = custom

    # 2. Fallbacks
    fallback_str = prefs.get("fallback_mirrors", "")
    fallbacks = [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip() and m.strip().rstrip("/") not in discard_set]
    prefs["fallback_mirrors"] = ", ".join(fallbacks)

    # 3. Last successful
    last_succ = normalize_mirror_url(prefs.get("last_successful_mirror", ""))
    if last_succ in discard_set:
        prefs["last_successful_mirror"] = ""

    counts = prefs.get("mirror_success_counts", {})
    if isinstance(counts, dict):
        prefs["mirror_success_counts"] = {
            normalize_mirror_url(m): c
            for m, c in counts.items()
            if normalize_mirror_url(m) and normalize_mirror_url(m) not in discard_set
        }

    lats = prefs.get("mirror_latencies", {})
    if isinstance(lats, dict):
        prefs["mirror_latencies"] = {
            normalize_mirror_url(m): ms
            for m, ms in lats.items()
            if normalize_mirror_url(m) and normalize_mirror_url(m) not in discard_set
        }

    # 4. Primary mirror
    primary = normalize_mirror_url(prefs.get("primary_mirror", ""))
    if primary in discard_set:
        remaining = fallbacks + custom
        prefs["primary_mirror"] = remaining[0] if remaining else "https://libgen.li"

def set_mirror_order(sorted_mirrors):
    """Updates mirror order in prefs, setting fastest as primary and others as fallbacks."""
    cleaned = []
    for m in sorted_mirrors:
        clean = normalize_mirror_url(m)
        if clean and clean not in cleaned:
            cleaned.append(clean)
    for m in PERMANENT_MIRRORS:
        if m not in cleaned:
            cleaned.append(m)

    if not cleaned:
        return
    primary = cleaned[0]
    prefs["primary_mirror"] = primary

    custom_set = set(normalize_mirror_url(m) for m in prefs.get("custom_mirrors", []))
    remaining = [m for m in cleaned[1:] if m not in custom_set]
    prefs["fallback_mirrors"] = ", ".join(remaining)


def record_cdn_speed(host, speed_kb):
    """Records CDN bandwidth and saves the top fastest CDNs to preferences."""
    with _prefs_lock:
        if not host or speed_kb <= 0:
            return
        host = host.lower().strip()
        cdns = prefs.get("fastest_cdns", {})
        if not isinstance(cdns, dict):
            cdns = {}
        prev = cdns.get(host, 0.0)
        if speed_kb > prev:
            cdns[host] = round(float(speed_kb), 1)
        # Keep top 10 fastest
        sorted_cdns = dict(sorted(cdns.items(), key=lambda item: item[1], reverse=True)[:10])
        prefs["fastest_cdns"] = sorted_cdns


def get_fastest_cdns():
    """Returns a list of (host, speed_kb) tuples sorted by bandwidth descending."""
    cdns = prefs.get("fastest_cdns", {})
    if not isinstance(cdns, dict):
        return []
    return sorted(cdns.items(), key=lambda item: item[1], reverse=True)


def get_search_history_filepath():
    """Returns absolute path to local search history file."""
    try:
        from calibre.utils.config import config_dir
        target_dir = os.path.join(config_dir, "plugins")
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "libgen_search_history.json")
    except Exception:
        return os.path.expanduser("~/.calibre_libgen_search_history.json")


def get_download_history_filepath():
    """Returns absolute path to local download history file."""
    try:
        from calibre.utils.config import config_dir
        target_dir = os.path.join(config_dir, "plugins")
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "libgen_download_history.json")
    except Exception:
        return os.path.expanduser("~/.calibre_libgen_download_history.json")


def _load_search_history_raw():
    filepath = get_search_history_filepath()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass

    # Migration from legacy plain-text libgen_search_history.txt if it exists
    try:
        from calibre.utils.config import config_dir
        old_path = os.path.join(config_dir, "plugins", "libgen_search_history.txt")
    except Exception:
        old_path = os.path.expanduser("~/.calibre_libgen_history.txt")

    if os.path.exists(old_path):
        try:
            with open(old_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            entries = [{"query": q, "timestamp": time.time()} for q in lines]
            _save_search_history_raw(entries)
            return entries
        except Exception:
            pass

    return []



def _atomic_write(filepath, data):
    import tempfile
    import os
    import json
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(filepath))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filepath)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise

def _save_search_history_raw(entries):
    filepath = get_search_history_filepath()
    try:
        _atomic_write(filepath, entries)
    except Exception:
        pass


def append_search_history(query):
    """Appends query to local search history with timestamp, enforcing max entries and retention days."""
    if not query or not query.strip():
        return
    query = query.strip()
    if not prefs.get("save_search_history", False):
        return

    now = time.time()
    retention_days = int(prefs.get("history_retention_days", 30))
    max_items = int(prefs.get("max_search_history", 50))
    cutoff = (now - (retention_days * 86400)) if retention_days > 0 else 0

    entries = _load_search_history_raw()
    if cutoff > 0:
        entries = [e for e in entries if e.get("timestamp", now) >= cutoff]

    if entries and entries[-1].get("query") == query:
        entries[-1]["timestamp"] = now
    else:
        entries.append({"query": query, "timestamp": now})

    if len(entries) > max_items:
        entries = entries[-max_items:]

    _save_search_history_raw(entries)


def get_search_history():
    """Reads historical search queries, filtering expired entries and keeping order."""
    if not prefs.get("save_search_history", False):
        return []
    now = time.time()
    retention_days = int(prefs.get("history_retention_days", 30))
    cutoff = (now - (retention_days * 86400)) if retention_days > 0 else 0

    entries = _load_search_history_raw()
    valid = []
    for e in entries:
        if cutoff > 0 and e.get("timestamp", now) < cutoff:
            continue
        q = e.get("query")
        if q:
            valid.append(q)
    return valid


def clear_search_history():
    """Wipes all search query history."""
    _save_search_history_raw([])


def _load_download_history_raw():
    filepath = get_download_history_filepath()
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def _save_download_history_raw(entries):
    filepath = get_download_history_filepath()
    try:
        _atomic_write(filepath, entries)
    except Exception:
        pass


def append_download_history(book, file_path=""):
    """Records a downloaded book entry with timestamp, enforcing max entries and retention days."""
    if not book:
        return
    now = time.time()
    retention_days = int(prefs.get("history_retention_days", 30))
    max_items = int(prefs.get("max_download_history", 50))
    cutoff = (now - (retention_days * 86400)) if retention_days > 0 else 0

    entries = _load_download_history_raw()
    if cutoff > 0:
        entries = [e for e in entries if e.get("timestamp", now) >= cutoff]

    title = getattr(book, "title", "") or ""
    author = getattr(book, "author", "") or ""
    ext = getattr(book, "extension", "") or ""
    size = getattr(book, "size", "") or ""
    md5 = getattr(book, "md5", "") or ""
    detail_url = getattr(book, "detail_url", "") or ""

    existing = False
    for e in entries:
        if (md5 and e.get("md5") == md5) or (title and e.get("title") == title and e.get("author") == author and e.get("extension") == ext):
            e["timestamp"] = now
            if file_path:
                e["file_path"] = file_path
            existing = True
            break

    if not existing:
        entries.append({
            "title": title,
            "author": author,
            "extension": ext,
            "size": size,
            "md5": md5,
            "detail_url": detail_url,
            "file_path": file_path,
            "timestamp": now,
        })

    if len(entries) > max_items:
        entries = entries[-max_items:]

    _save_download_history_raw(entries)


def get_download_history():
    """Returns list of downloaded book records, filtering expired entries."""
    now = time.time()
    retention_days = int(prefs.get("history_retention_days", 30))
    cutoff = (now - (retention_days * 86400)) if retention_days > 0 else 0

    entries = _load_download_history_raw()
    if cutoff > 0:
        return [e for e in entries if e.get("timestamp", now) >= cutoff]
    return entries


def clear_download_history():
    """Wipes all download history records."""
    _save_download_history_raw([])


def clear_all_history(history_type="all"):
    """Wipes history ('search', 'download', or 'all')."""
    if history_type in ("search", "all"):
        clear_search_history()
    if history_type in ("download", "all"):
        clear_download_history()


def cleanup_expired_history():
    """Purges expired entries across search and download history according to retention policy."""
    now = time.time()
    retention_days = int(prefs.get("history_retention_days", 30))
    if retention_days <= 0:
        return
    cutoff = now - (retention_days * 86400)

    # Clean search history
    s_entries = _load_search_history_raw()
    s_filtered = [e for e in s_entries if e.get("timestamp", now) >= cutoff]
    if len(s_filtered) != len(s_entries):
        _save_search_history_raw(s_filtered)

    # Clean download history
    d_entries = _load_download_history_raw()
    d_filtered = [e for e in d_entries if e.get("timestamp", now) >= cutoff]
    if len(d_filtered) != len(d_entries):
        _save_download_history_raw(d_filtered)


def get_pending_searches():
    """Returns list of pending/failed (zero-result) search queries."""
    pending = prefs.get("pending_searches", [])
    if isinstance(pending, list):
        return [p.strip() for p in pending if p and isinstance(p, str) and p.strip()]
    return []


def add_pending_search(query):
    """Appends query to pending searches list if not already present."""
    if not query or not query.strip():
        return
    query = query.strip()
    pending = get_pending_searches()
    if query not in pending:
        pending.insert(0, query)  # Most recent first
        # Keep up to 100 pending searches
        pending = pending[:100]
        prefs["pending_searches"] = pending


def remove_pending_search(query):
    """Removes query from pending searches list."""
    if not query:
        return
    query = query.strip()
    pending = get_pending_searches()
    if query in pending:
        pending = [p for p in pending if p != query]
        prefs["pending_searches"] = pending


def clear_pending_searches():
    """Wipes all pending searches."""
    prefs["pending_searches"] = []


SUPPORTED_LANGUAGES = [
    "Any",
    "English",
    "Spanish",
    "French",
    "German",
    "Russian",
    "Italian",
    "Portuguese",
    "Chinese",
    "Japanese",
]

SUPPORTED_FORMATS = [
    "Any",
    "EPUB",
    "PDF",
    "MOBI",
    "AZW3",
    "DJVU",
    "CBR",
    "CBZ",
]

FILTER_MODES = [
    "Prioritize",  # Display matching items first, but keep others
    "Strict",      # Only return items matching preferred language / format
]


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Mirror Settings Group
        mirror_group = QGroupBox("Mirror Settings")
        mirror_layout = QFormLayout(mirror_group)

        self.primary_mirror_edit = QLineEdit(self)
        self.primary_mirror_edit.setText(prefs.get("primary_mirror", "https://libgen.li"))
        mirror_layout.addRow("Primary Mirror URL:", self.primary_mirror_edit)

        self.fallback_mirrors_edit = QLineEdit(self)
        self.fallback_mirrors_edit.setText(
            prefs.get(
                "fallback_mirrors",
                "https://libgen.vg, https://libgen.gl, https://libgen.bz, https://libgen.la, https://libgen.is",
            )
        )
        mirror_layout.addRow("Fallback Mirrors (comma separated):", self.fallback_mirrors_edit)

        self.timeout_spin = QSpinBox(self)
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setValue(int(prefs.get("timeout", 20)))
        mirror_layout.addRow("Connection Timeout:", self.timeout_spin)

        self.search_timeout_spin = QSpinBox(self)
        self.search_timeout_spin.setRange(3, 30)
        self.search_timeout_spin.setSuffix(" s")
        self.search_timeout_spin.setValue(int(prefs.get("search_timeout", 8)))
        mirror_layout.addRow("Search Timeout:", self.search_timeout_spin)

        self.layout.addWidget(mirror_group)

        # Filter & Preference Settings Group
        filter_group = QGroupBox("Search & Format Preferences")
        filter_layout = QFormLayout(filter_group)

        # Language selection
        self.language_combo = QComboBox(self)
        self.language_combo.addItems(SUPPORTED_LANGUAGES)
        current_lang = prefs.get("preferred_language", "English")
        idx = self.language_combo.findText(current_lang)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
        else:
            self.language_combo.addItem(current_lang)
            self.language_combo.setCurrentText(current_lang)
        self.language_combo.setEditable(True)
        filter_layout.addRow("Lock / Preferred Language:", self.language_combo)

        # Format selection
        self.format_combo = QComboBox(self)
        self.format_combo.addItems(SUPPORTED_FORMATS)
        current_fmt = prefs.get("preferred_format", "Any").upper()
        f_idx = self.format_combo.findText(current_fmt)
        if f_idx >= 0:
            self.format_combo.setCurrentIndex(f_idx)
        filter_layout.addRow("Lock / Preferred Format:", self.format_combo)

        # Filter Mode selection
        self.filter_mode_combo = QComboBox(self)
        self.filter_mode_combo.addItems(FILTER_MODES)
        cur_mode = prefs.get("filter_mode", "Prioritize")
        m_idx = self.filter_mode_combo.findText(cur_mode)
        if m_idx >= 0:
            self.filter_mode_combo.setCurrentIndex(m_idx)
        filter_layout.addRow("Filter Enforcement:", self.filter_mode_combo)

        # Max Results
        self.max_results_spin = QSpinBox(self)
        self.max_results_spin.setRange(1, 1000)
        self.max_results_spin.setValue(int(prefs.get("max_results", 5)))
        filter_layout.addRow("Max Results per Search:", self.max_results_spin)

        # History & Retention Preferences
        history_group = QGroupBox("History & Retention Preferences")
        history_layout = QFormLayout(history_group)

        self.save_history_checkbox = QCheckBox("Save search query history and enable autocomplete", self)
        self.save_history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
        self.save_history_checkbox.setToolTip(f"Preserves searched queries locally in {get_search_history_filepath()}")
        history_layout.addRow("Search History:", self.save_history_checkbox)

        self.max_search_history_spin = QSpinBox(self)
        self.max_search_history_spin.setRange(5, 1000)
        self.max_search_history_spin.setValue(int(prefs.get("max_search_history", 50)))
        history_layout.addRow("Max Search History Entries:", self.max_search_history_spin)

        self.max_download_history_spin = QSpinBox(self)
        self.max_download_history_spin.setRange(5, 1000)
        self.max_download_history_spin.setValue(int(prefs.get("max_download_history", 50)))
        history_layout.addRow("Max Download History Entries:", self.max_download_history_spin)

        self.retention_days_spin = QSpinBox(self)
        self.retention_days_spin.setRange(0, 365)
        self.retention_days_spin.setSuffix(" days")
        self.retention_days_spin.setSpecialValueText("Never (Keep indefinitely)")
        self.retention_days_spin.setValue(int(prefs.get("history_retention_days", 30)))
        self.retention_days_spin.setToolTip("Auto-clears search and download history older than X days. Set to 0 to disable.")
        history_layout.addRow("Clear History After:", self.retention_days_spin)

        self.clear_history_btn = QPushButton("Clear All History Now", self)
        self.clear_history_btn.clicked.connect(self._confirm_clear_history)
        history_layout.addRow("", self.clear_history_btn)

        self.layout.addWidget(filter_group)
        self.layout.addWidget(history_group)

        # Informational note
        note = QLabel(
            "<i>Note: 'Strict' filter mode only shows books matching both preferred language "
            "and format. 'Prioritize' mode surfaces matching books to the top.</i>"
        )
        note.setWordWrap(True)
        self.layout.addWidget(note)
        self.layout.addStretch()

    def _confirm_clear_history(self):
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

    def save_settings(self):
        prefs["primary_mirror"] = self.primary_mirror_edit.text().strip()
        prefs["fallback_mirrors"] = self.fallback_mirrors_edit.text().strip()
        prefs["timeout"] = self.timeout_spin.value()
        prefs["preferred_language"] = self.language_combo.currentText().strip()
        prefs["preferred_format"] = self.format_combo.currentText().strip().upper()
        prefs["filter_mode"] = self.filter_mode_combo.currentText().strip()
        prefs["max_results"] = self.max_results_spin.value()
        prefs["search_timeout"] = self.search_timeout_spin.value()
        prefs["save_search_history"] = self.save_history_checkbox.isChecked()
        prefs["max_search_history"] = self.max_search_history_spin.value()
        prefs["max_download_history"] = self.max_download_history_spin.value()
        prefs["history_retention_days"] = self.retention_days_spin.value()
