---
format: gemini-readable-change-log
project: libgen-downloader
updated: 2026-09-15
---

# Internal Change Log

## 2026-09-15

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
