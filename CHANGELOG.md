# Changelog

## [v1.11b] - 2026-09-15

- **Reorderable Dialog Tabs:** Tabs can now be rearranged via drag-and-drop (`QTabWidget.setMovable(True)`), with dynamic tab switching and order persistence across restarts.
- **Queue Segmentation & Retention Policy:** Separate views for `Queued`, `Downloading`, `Downloaded`, and `Failed` (removed "All"). Auto-prunes history records older than $X$ days with configurable history limits.
- **Persistent Table Column Widths:** Preserves header column dimensions across dialog restarts for search results, queue, and mirrors tables.
- **Pending Searches Tracker:** Zero-result queries are automatically captured in a quick-retry dropdown.
- **Multi-Language Selector:** Combobox with individual checkable language items and compact short code badges.
- **⚡ Fast Mode:** Probes mirrors with a tight 3s timeout, instantly routing dead or slow mirrors to the Failed queue for rapid recovery.
- **Discard Dead Mirrors:** One-click removal of failed or unreachable mirrors after connection tests.
- **Qt Event Loop Fix:** Resolved `QApplication` import error during batch event processing.

## [v1.0.1 "Godzila"] - 2026-09-12

- **Fixed Failed Downloads:** Resolved silent download and resolution failures across newer mirrors (`.li`, `.vg`, `.la`) caused by anti-scraping checks.
- **Animated Cover Previews:** Added a smooth text spinner animation (`⠋ 📖`) in the preview pane while covers load.
- **Instant Cover Caching:** Book covers are now cached in-memory; previously loaded covers display with zero latency.
- **Preserved Book Proportions:** Fixed cover image stretching so book covers retain their natural aspect ratios.
- **Version Indicators:** Current version is now prominently visible in the window title and in the bottom status bar next to the cat.

## [v1.0.0 "Godzila"] - 2026-09-11

- **Animated Status Cat:** Added an ASCII companion cat (`(=^.^=)`) in the status bar that animates and reacts while searching and downloading.
- **Faster Downloads:** Queue up entire book series and download up to 3 books simultaneously with live speed meters.
- **Book Cover Previews:** Click any book in your search results or queue to instantly preview its original book cover.
- **Compact Two-Row Search Bar:** Reorganized all search options, category filters, and mirrors into a tidy two-row panel so it fits nicely on any screen size.
- **Live Mirror Auto-Recovery:** Automatically finds and connects to working LibGen mirrors whenever your default one is slow or unreachable.
- **Retro ASCII Progress:** Clean text progress bars inside the queue table replace clunky loading bars.
- **Download Summaries:** Shows total time taken, file sizes, and completion stats after every bulk download run.
