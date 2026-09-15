# Changelog

## [v1.50] - 2026-09-15

### Highlights
- **Hardcover Reading Lists:** Sync "Want to Read" and custom shelves straight into your download queue with automatic duplicate detection.
- **Search Existing Library Books:** Highlight books in Calibre and batch-search working mirrors without manual typing.
- **Optimized Download Speeds:** 512 KB streaming buffers, smart connection limits, and automatic Cloudflare 503 bypasses for reliable transfers.
- **Modernized UI & Live Metrics:** Real-time speed tiers, exact MB transferred, ETA countdowns, and movable tabs.
- **Instant Mirror Failover:** Automatic fallback to fastest responsive mirrors with live latency indicators.

### Community & Discussion
- 💬 **Discord:** [Join the Discord Community](https://discord.gg/x2cZK7MT)
- 🤖 **Reddit:** [r/booksdev](https://reddit.com/r/booksdev)

### Detailed Changes
- **Hardcover Reading List & Shelf Downloader:** Directly sync personal reading lists and shelves ("Want to Read", "Currently Reading", custom lists) via Hardcover.app API token. Includes automatic skipping of books already in your Calibre library, ISBN matching, and one-click queue staging.
- **Search Selected Calibre Book Records:** Select one or multiple books in your Calibre library and click "Search Record(s)" to initiate an automated serialized search queue across mirrors without typing queries.
- **Configurable Download Concurrency & 512 KB Buffer:** New UI spinbox for concurrent file downloads (1–4), defaulted to 1 to maximize bandwidth concentration and defeat CDN rate-limiting, backed by quadrupled 512 KB transfer buffers.
- **Streamlined Top Search Bar:** Clean primary row with search input, format, language, search, and Hardcover; secondary parameters tucked into an expandable `[⚙ Filters ▾]` drawer that persists its state across sessions.
- **Modern Vector Progress Bars & Verbose Metrics:** Replaced retro ASCII bars with native `ProgressBarDelegate` rendering smooth rounded progress bars showing detailed bytes transferred (`MB / MB`), live speed icons (`⚡`, `🚀`, `📥`), and ETA countdowns.
- **Dedicated Bulk Download Progress Bar:** Added an overall session progress bar in the Queue tab showing batch completion (`X / Y books (Z%)`), speed, and ETA.
- **CDN Hotlink 503 Resolution:** Fixed Cloudflare HTTP 503 errors by dynamically injecting valid mirror origin Referers across multi-segment and single-stream transfers.
- **Tuned Segmented Concurrency:** Calibrated range-request concurrency to 2–3 parallel connections per file with per-segment User-Agent rotation to prevent Cloudflare rate-limiting.
- **Emoji-Rich Live Mirror & CDN Status:** Real-time side panel showing connection states with indicators (`🟢`/`🔴`, `📶`, `⚡`), and session-end fastest CDN rankings with trophies (`🏆`, `🥈`, `🥉`).
- **Search Progress Bar:** Added an animated progress bar in the search tab for live mirror queries and serialized Calibre search steps.
- **Collapsible Activity Log:** Converted the static 120px activity log into an expandable panel (`▶ Live Activity Log`) to maximize table rows.
- **IndexError & Download Race Fix:** Resolved `IndexError` in `on_item_progress` / `on_item_status` with bounds checking and protected queue modifications during active downloads.
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
