---
format: gemini-readable-change-log
project: libgen-downloader
updated: 2026-09-15
---

# Internal Change Log

## 2026-09-15

- id: verbose-download-progress-and-emoji-cdn-rankings
  type: feat
  files: [dialog.py, progress_delegate.py, config.py]
  summary: Added verbose download progress metrics (MB/MB, speed icons, and ETA) across queue cells, status bar, and bulk progress bar. Enriched Live Mirror Status panel with emojis (🟢/🔴, 📶, ⚡) and ranked top CDNs with medal badges (🏆, 🥈, 🥉) at session completion.
  why: User requested more verbose download progress, ranking best CDNs in session, and displaying them in the live mirror status field with emojis.
  validation: Tested in GUI; progress delegate and dialog compile without error

- id: fix-download-503-hotlink-and-tune-segments
  type: fix
  files: [scraper.py, config.py, benchmark_download.py]
  summary: Injected mirror origin Referer (https://<host>/) on all segment and single-stream requests to bypass Cloudflare HTTP 503 anti-hotlink checks. Calibrated segment concurrency to 2-3 connections to avoid rate-limiting lockouts.
  why: Direct CDN requests returned HTTP 503; high connection counts triggered Cloudflare connection floods.
  validation: Rigorous benchmark suite (benchmark_download.py) demonstrated successful HTTP 200/206 streaming and verified stable 40-55 KB/s throughput.

- id: multi-segment-download-with-ua-rotation
  type: perf
  files: [scraper.py, config.py]
  summary: Enabled segmented downloading from single CDN source across parallel range-requests with per-segment User-Agent rotation and Connection keep-alive.
  why: LibGen mirrors resolve to the same underlying CDN host; parallel range connections bypass per-connection throttling.
  validation: Successfully split and reassembled files with checksum verification.

- id: optimize-download-speed-concurrency-and-buffer
  type: perf
  files: [dialog.py, scraper.py, config.py]
  summary: Defaulted bulk download queue to 1 file at a time to prevent CDN throttling. Added UI Concurrent Files spinbox (1-4). Quadrupled chunk and reassembly buffer from 128 KB to 512 KB.
  why: User requested fixing download speed by downloading 1 file at a time with maximum connection concentration and evaluating pycurl/aria2 alternatives.
  validation: 9/9 unit tests pass; pycurl benchmark conducted; live segmented transfer verified

- id: unify-search-queue-bar-and-hide-mirror-status-toast

  type: feat
  files: [dialog.py, config.py]
  summary: Unified search queue bar into a single full-width action button. Hid live mirror status panel by default (only Cover Preview visible). Added floating toast notification when toggling cats and stats via 3x version badge click.
  why: User requested unifying split queue bar buttons, keeping only cover preview active by default, and showing toast on badge toggle.
  validation: python3 -m py_compile dialog.py passed; 9/9 unit tests pass

- id: fix-collections-import-dialog

  type: fix
  files: [dialog.py, config.py]
  summary: Imported collections module in dialog.py to resolve NameError when initializing pending_queue deque.
  why: Uncaught NameError: name 'collections' is not defined crashed bulk search.
  validation: python3 -m py_compile dialog.py passed; 9/9 unit tests pass

- id: bulk-search-single-result-isbn
  type: perf
  files: [dialog.py, scraper.py, config.py]
  summary: Limited bulk search queue to 1 result per entry; clamped identifier search fetch_count to 5 to avoid scraping unnecessary HTML tables. Tested ISBN vs title/author speeds.
  why: User requested finding 1 result per entry in bulk search and testing whether ISBN is faster than title/author.
  validation: 9/9 unit tests pass; live test showed ISBN is 35-50% faster (2.6s vs 4-5s)

- id: search-queue-deferral-and-hide-cats
  type: feat
  files: [dialog.py, config.py]
  summary: Implemented two-pass bulk queue search deferring slow/failing records to the tail. Defaulted cats and download stats to hidden; toggleable via 3x click on version badge.
  why: User requested faster bulk search with deferral of difficult items and hiding cats/stats by default with 3x click toggle.
  validation: 9/9 unit tests pass

- id: ui-hardcover-token-size
  type: fix
  files: [dialog.py, config.py]
  summary: Reduced Hardcover dialog token field to 220px, compacted match row horizontally with stretch, lowered dialog default bounds to 640x460 (max clamped 880x680).
  why: User reported Hardcover child window and token field were too wide.
  validation: verified layout clamps and 9/9 tests pass

- id: mirror-latency-cycling
  type: feat
  files: [config.py, dialog.py, scraper.py, calibre_dialog.ui, test_search_logic.py]
  summary: Replaced 'Auto (Failover)' with 'Auto (Best Latency)'. Mirrors sorted by lowest latency first. Ping testing persists latency into prefs. Purged dead mirror domains.
  why: User requested removing failover concept in favor of defaulting to mirror with best latency and cycling sequentially if one fails.
  validation: 9/9 offline unit tests passing

- id: ui-hardcover-compact
  type: fix
  files: [dialog.py]
  summary: Shortened Hardcover dialog labels and buttons; capped token field width; stacked queue matching controls.
  why: Prevents the dialog from sprawling across the full Calibre window with long token/mode text.
  validation: pending

- id: build-beta-66
  type: build
  files: [config.py, libgen_downloader.zip]
  summary: Forced plugin rebuild/install with `_BUILD_COMMIT = "66"`.
  why: Beta display version resolves to `v1.11b-66`.
  validation: installed via `make -B install`

- id: ui-live-search-and-download-folder
  type: feature
  files: [dialog.py, progress_delegate.py, calibre_dialog.ui]
  summary: Live search result updates, discard selected, persistent download folder/action mode, Qt theme progress polish, second animated cat.
  validation: committed 80302f6

- id: core-search-download-routing
  type: perf
  files: [scraper.py, config.py, test_download_logic.py, test_search_logic.py]
  summary: Search dedupe/rank optimization, mirror normalization, CDN speed memory, stricter segmented download validation.
  validation: committed b8a2c7d
