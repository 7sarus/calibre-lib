---
tags: [libgen, downloads, performance]
date: 2026-09-15
---

# Download Logic

- Start transferring after two distinct working stream URLs respond. Cancel queued probes; already-running probes finish within their network timeouts.
- Combine only distinct range streams with matching advertised sizes. Matching sizes do not prove identical contents; no checksum verification was added.
- Require HTTP 206 and the exact requested Content-Range before writing a segment. Reject oversized responses immediately.
- Roll back discarded segment bytes from progress before retrying.
- Reject empty or truncated streams with a known Content-Length; report final progress for successful streams.
- Rank range-capable stream URLs by learned CDN throughput and current probe speed before assigning parallel segments.
- Record successful segment throughput per CDN so later downloads prefer the fastest observed streams.
- Downloads now use a persistent user-readable folder instead of a worker-owned temp directory.
- Queue action can be switched between importing to Calibre after download and saving files to the folder only.
- Default persistent download folder is now `~/Downloads/callib`.
- Hardcover opens from cached shelves/books by default; refresh buttons are the only API path.
- Main child panel sizes, Hardcover dialog/table sizing, and import review dialog/table sizing are persisted.
- Existing sequential mirror fallback remains available outside fast mode.

Validation: offline regression tests passed using `python3 -B -m unittest test_download_logic test_search_logic -v`; touched files compile with `python3 -B -m py_compile dialog.py config.py scraper.py`; `git diff --check` passed. No build, installation, or live bandwidth benchmark performed.

Pending: sync this note into the external Obsidian index/dashboard when that directory is writable. Run a live benchmark to quantify speed changes.
