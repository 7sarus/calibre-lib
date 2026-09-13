#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration settings and preferences UI for the LibGen Store plugin.
"""

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
)

# Store configuration under Calibre's standard plugin config path
prefs = JSONConfig("plugins/libgen_store")

# Default preferences
prefs.defaults["primary_mirror"] = "https://libgen.li"
prefs.defaults["fallback_mirrors"] = (
    "https://libgen.vg, https://libgen.gl, https://libgen.bz, https://libgen.la, https://libgen.is"
)
prefs.defaults["preferred_language"] = "English"
prefs.defaults["preferred_format"] = "Any"
prefs.defaults["filter_mode"] = "Prioritize"
prefs.defaults["max_results"] = 25
prefs.defaults["timeout"] = 20

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
        self.max_results_spin.setRange(5, 100)
        self.max_results_spin.setValue(int(prefs.get("max_results", 25)))
        filter_layout.addRow("Max Results per Search:", self.max_results_spin)

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

