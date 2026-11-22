#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Diagnostic Log Collector Service for LibGen Downloader plugin.
Gathers environment details, Calibre & plugin versions, mirror latency state,
and session logs, and copies them formatted to the system clipboard.
"""

import sys
import platform
from datetime import datetime, timezone

try:
    from qt.core import QApplication
except ImportError:
    QApplication = None

try:
    from calibre.constants import __version__ as calibre_version
except Exception:
    calibre_version = "Unknown"

try:
    from calibre_plugins.libgen_store.config import (
        PLUGIN_VERSION_STR,
        get_active_backend,
        get_mirrors,
        prefs,
    )
except ImportError:
    try:
        from config import (
            PLUGIN_VERSION_STR,
            get_active_backend,
            get_mirrors,
            prefs,
        )
    except Exception:
        PLUGIN_VERSION_STR = "Unknown"
        get_active_backend = lambda: "Unknown"
        get_mirrors = lambda: []
        prefs = {}


def collect_diagnostics(session_log=""):
    """
    Assembles a Markdown diagnostic report containing:
    - Plugin, Calibre, Python, and OS versions
    - Active backend and filter preferences
    - Mirror list with latency records
    - Timestamped session activity log
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    py_info = f"{platform.python_implementation()} {sys.version.split()[0]}"

    backend = get_active_backend() if callable(get_active_backend) else "Unknown"
    format_pref = prefs.get("preferred_format", "Any") if hasattr(prefs, "get") else "Any"
    lang_pref = prefs.get("preferred_language", "English") if hasattr(prefs, "get") else "English"
    filter_mode = prefs.get("filter_mode", "Prioritize") if hasattr(prefs, "get") else "Prioritize"
    max_results = prefs.get("max_results", 5) if hasattr(prefs, "get") else 5

    mirrors = get_mirrors() if callable(get_mirrors) else []
    latencies = prefs.get("mirror_latencies", {}) if hasattr(prefs, "get") else {}
    success_counts = prefs.get("mirror_success_counts", {}) if hasattr(prefs, "get") else {}
    primary_mirror = prefs.get("primary_mirror", "") if hasattr(prefs, "get") else ""

    mirror_lines = []
    for m in mirrors:
        lat = latencies.get(m, "-")
        lat_str = f"{lat}ms" if isinstance(lat, (int, float)) and lat > 0 else "untested/err"
        succ = success_counts.get(m, 0)
        tag = " [Primary]" if m == primary_mirror else ""
        mirror_lines.append(f"  - {m}{tag}: latency={lat_str}, success_count={succ}")

    if not mirror_lines:
        mirror_lines = ["  (none configured)"]

    clean_log = (session_log or "").strip()
    if not clean_log:
        clean_log = "(No activity logged in current session)"

    mirrors_block = "\n".join(mirror_lines)
    report = f"""### LibGen Downloader Diagnostic Report
- **Generated**: {now_utc}
- **Plugin Version**: `{PLUGIN_VERSION_STR}`
- **Calibre Version**: `{calibre_version}`
- **OS / Platform**: `{os_info}`
- **Python**: `{py_info}`
- **Active Backend**: `{backend}`
- **Filters**: Mode=`{filter_mode}`, Format=`{format_pref}`, Lang=`{lang_pref}`, Max=`{max_results}`

#### Mirror Pool & Latency
{mirrors_block}

#### Session Activity Log
```text
{clean_log}
```"""
    return report.strip()


def copy_diagnostics_to_clipboard(session_log=""):
    """
    Generates diagnostic report and sets system clipboard text.
    Returns the report string.
    """
    report = collect_diagnostics(session_log=session_log)
    if QApplication is not None:
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(report)
        except Exception:
            pass
    return report
