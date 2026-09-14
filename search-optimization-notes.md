---
tags: [libgen, search, performance]
date: 2026-09-15
---

# Search Optimization Notes

- Scope: internal search logic only; visible search behavior and ranking contract kept unchanged.
- Deduped mirror dispatch before creating futures, so duplicate configured mirrors no longer submit duplicate network searches.
- Added zero-mirror guard to avoid executor failure when configuration normalizes to no usable mirrors.
- Precomputed search URL parameters once per search instead of rebuilding field/category mapping inside every mirror worker.
- Reused the latest ranked result set for the final return path, avoiding a second full dedupe/rank pass after all mirrors complete.
- Bulk record searches now run in up to three parallel lanes, each lane preferring a different top mirror to share load.
- Added offline tests for duplicate mirror dispatch and final rank reuse.

Validation:

- `python3 -B -m unittest test_search_logic test_download_logic -v`
- `git diff --check`
- `python3 -B -m py_compile dialog.py config.py scraper.py hardcover.py`

Pending:

- Sync this note into `/home/thomas/Documents/tech/` when external notes are writable.
- Run live benchmark only when explicitly requested: `Foundation`, 5 results, queue/download all.
