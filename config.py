#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration settings and preferences UI for the LibGen Store plugin.
"""

import os
from calibre.utils.config import JSONConfig
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
)

# Plugin Version definitions
PLUGIN_VERSION = (1, 10, 0, "b")
_BASE_VERSION_STR = "v1.10b"
_BUILD_COMMIT = "449"


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

# Default preferences
prefs.defaults["primary_mirror"] = "https://libgen.li"
prefs.defaults["fallback_mirrors"] = (
    "https://libgen.rs, https://libgen.is, https://libgen.st, "
    "https://libgen.vg, https://libgen.gl, https://libgen.bz, "
    "https://libgen.gs, https://libgen.lc, https://libgen.la"
)
prefs.defaults["preferred_language"] = "English"
prefs.defaults["preferred_format"] = "Any"
prefs.defaults["custom_mirrors"] = []
prefs.defaults["selected_mirror"] = "Auto"
prefs.defaults["search_field"] = "All Fields"
prefs.defaults["search_category"] = "All Categories"
prefs.defaults["filter_mode"] = "Prioritize"
prefs.defaults["last_search_query"] = ""
prefs.defaults["last_successful_mirror"] = ""
prefs.defaults["max_results"] = 5
prefs.defaults["show_download_stats"] = True
prefs.defaults["fastest_cdns"] = {}
prefs.defaults["unique_results"] = True
prefs.defaults["fast_mode"] = False
prefs.defaults["preferred_languages"] = ["Any"]
prefs.defaults["save_search_history"] = False

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
    """Returns an ordered list of unique mirrors. Prioritizes last_successful_mirror at the top."""
    primary = prefs.get("primary_mirror", "https://libgen.li").strip().rstrip("/")
    fallback_str = prefs.get("fallback_mirrors", "")
    fallbacks = [m.strip().rstrip("/") for m in fallback_str.split(",") if m.strip()]
    custom = [m.strip().rstrip("/") for m in prefs.get("custom_mirrors", []) if m.strip()]

    mirrors = []
    last_succ = prefs.get("last_successful_mirror", "").strip().rstrip("/")
    if last_succ:
        mirrors.append(last_succ)

    for m in [primary] + fallbacks + custom:
        if m and m not in mirrors:
            mirrors.append(m)
    return mirrors

def record_successful_mirror(mirror_url):
    """Persists the specified mirror as the last successful mirror for next operations."""
    if not mirror_url:
        return
    clean = mirror_url.strip().rstrip("/")
    if clean:
        prefs["last_successful_mirror"] = clean

def add_custom_mirror(url):
    url = url.strip().rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    custom = list(prefs.get("custom_mirrors", []))
    if url not in custom:
        custom.append(url)
        prefs["custom_mirrors"] = custom
    return url

def remove_custom_mirror(url):
    url = url.strip().rstrip("/")
    custom = [m for m in prefs.get("custom_mirrors", []) if m.rstrip("/") != url]
    prefs["custom_mirrors"] = custom

def discard_mirrors(urls_to_discard):
    """Removes the given URLs from primary, fallback, custom, and last_successful mirrors."""
    discard_set = set(u.strip().rstrip("/") for u in urls_to_discard if u)
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
    last_succ = prefs.get("last_successful_mirror", "").strip().rstrip("/")
    if last_succ in discard_set:
        prefs["last_successful_mirror"] = ""

    # 4. Primary mirror
    primary = prefs.get("primary_mirror", "").strip().rstrip("/")
    if primary in discard_set:
        remaining = fallbacks + custom
        prefs["primary_mirror"] = remaining[0] if remaining else "https://libgen.li"

def set_mirror_order(sorted_mirrors):
    """Updates mirror order in prefs, setting fastest as primary and others as fallbacks."""
    if not sorted_mirrors:
        return
    primary = sorted_mirrors[0].strip().rstrip("/")
    prefs["primary_mirror"] = primary

    custom_set = set(m.rstrip("/") for m in prefs.get("custom_mirrors", []))
    remaining = [m.rstrip("/") for m in sorted_mirrors[1:] if m.rstrip("/") not in custom_set]
    prefs["fallback_mirrors"] = ", ".join(remaining)


def record_cdn_speed(host, speed_kb):
    """Records CDN bandwidth and saves the top fastest CDNs to preferences."""
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
def get_search_history_filepath():
    """Returns absolute path to local search history file."""
    try:
        from calibre.utils.config import config_dir
        target_dir = os.path.join(config_dir, "plugins")
        os.makedirs(target_dir, exist_ok=True)
        return os.path.join(target_dir, "libgen_search_history.txt")
    except Exception:
        return os.path.expanduser("~/.calibre_libgen_history.txt")


def append_search_history(query):
    """Appends query to local search history file if enabled, avoiding consecutive duplicates."""
    if not query or not query.strip():
        return
    query = query.strip()
    if not prefs.get("save_search_history", False):
        return
    filepath = get_search_history_filepath()
    try:
        last_line = None
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
                if lines:
                    last_line = lines[-1]
        if last_line != query:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(query + "\n")
    except Exception:
        pass


def get_search_history():
    """Reads historical search queries from local file."""
    if not prefs.get("save_search_history", False):
        return []
    filepath = get_search_history_filepath()
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return [l.strip() for l in f if l.strip()]
    except Exception:
        pass
    return []


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

        # Search Query History (Opt-in)
        self.save_history_checkbox = QCheckBox("Save search query history to local file", self)
        self.save_history_checkbox.setChecked(bool(prefs.get("save_search_history", False)))
        self.save_history_checkbox.setToolTip(f"Preserves searched queries locally in {get_search_history_filepath()}")
        filter_layout.addRow("Search History:", self.save_history_checkbox)

        self.layout.addWidget(filter_group)

        # Informational note
        note = QLabel(
            "<i>Note: 'Strict' filter mode only shows books matching both preferred language "
            "and format. 'Prioritize' mode surfaces matching books to the top.</i>"
        )
        note.setWordWrap(True)
        self.layout.addWidget(note)
        self.layout.addStretch()

    def save_settings(self):
        prefs["primary_mirror"] = self.primary_mirror_edit.text().strip()
        prefs["fallback_mirrors"] = self.fallback_mirrors_edit.text().strip()
        prefs["timeout"] = self.timeout_spin.value()
        prefs["preferred_language"] = self.language_combo.currentText().strip()
        prefs["preferred_format"] = self.format_combo.currentText().strip().upper()
        prefs["filter_mode"] = self.filter_mode_combo.currentText().strip()
        prefs["max_results"] = self.max_results_spin.value()
        prefs["save_search_history"] = self.save_history_checkbox.isChecked()

