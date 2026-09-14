---
format: gemini-readable-change-log
project: libgen-downloader
updated: 2026-09-15
---

# Internal Change Log

## 2026-09-15

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
