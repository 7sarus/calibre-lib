---
tags: [calibre, python, qt, scraping, libgen, handover]
date: 2026-10-10
---

# calibre-lib (`calibre-libgen-store`) — LLM Context & Handover Guide

> **Note for AI Agents**: Read this file first, before `AGENTS.md`, before inspecting code, before running any task.
> Project state is summarized here so you never have to re-derive it by reading 8,900 lines of Python.

---

## 1. Project Overview

A **Calibre User Interface Action plugin** (`calibre_plugins.libgen_store`) that adds a toolbar button (`Ctrl+Shift+L`) for searching, queueing, and bulk-downloading books into a Calibre library.

- **Upstream repo**: `git@github.com:7sarus/calibre-lib.git` (origin + upstream both point here).
- **License**: WTFPL. Adapted from [`obsfx/libgen-downloader`](https://github.com/obsfx/libgen-downloader).
- **Status**: Beta. Active branch `beta`, version `v1.70b`.
- **Runtime**: Calibre's **bundled Python 3** and Qt bindings only. Imports must use `qt.core` (Qt5/Qt6 shim), **never** bare `PyQt5`/`PyQt6`.
- **Hard rule**: zero external dependencies. Only Calibre-bundled `bs4`, `calibre.browser`, `qt.core`, `lxml` (optional, auto-detected).

---

## 2. Repo & Branch State

| Item | Value |
|---|---|
| Active branch | `beta` (do **not** promote to `master` without explicit instruction) |
| Other branches | `master`, `feat/bookracy`, `backup-before-rebase` |
| Commit count | 147 — mirrors `config.py:_BUILD_COMMIT` and every `v1.xxb-NNN` artifact |
| Latest commit | `5a282fa` Unify backend separation across search, queue, workers, preferences |
| Dirty tree | `test_plugin.py`, `test_search_logic.py`, `test_download_logic.py` are **deleted, uncommitted**; `AGENTS.md` modified; `llm.md` untracked |
| Built artifacts | `libgen_downloader*.zip` are gitignored build output, not sources |

---

## 3. Environment & Commands

| Task | Command |
|---|---|
| Build plugin zip | `make build` (stamps `_BUILD_COMMIT` via `sed` before zipping) |
| Build + install into Calibre | `make install` (runs `calibre-customize -a`) |
| Uninstall plugin | `make uninstall` |
| Test in Calibre debug | `make test` (wraps `calibre-debug test_plugin.py`) |
| Clean artifacts | `make clean` |
| Beta release | `make release-beta TAG=v1.50b` — requires `TAG`, pushes tag + GitHub pre-release |
| Official release | `make release TAG=v1.50` — only after explicit promotion |
| Mirror latency probe | `python3 ping_mirrors.py` |
| Download throughput benchmark | `python3 benchmark_download.py` |
| Search benchmark | `python3 benchmark_search.py` / `benchmark.py` |

**Do not run build/install commands autonomously.** Hand the user the exact command.

**Benchmark protocol** (fixed, from `AGENTS.md`): query `Foundation`, max 5 results, queue and download all five, report elapsed time, total size, bandwidth, fastest CDNs. Data stays local — no external telemetry.

---

## 4. Architecture

### Module map (line counts, 2026-10-10)

| File | Lines | Role |
|---|---|---|
| `dialog.py` | 3821 | **Monolith UI**: multi-tab dialog, queue segmentation, review modal, Hardcover importer, library context-menu search |
| `scraper.py` | 1860 | Mirror resolution, search HTML parsing (BeautifulSoup), segmented download, anti-scraping |
| `config.py` | 857 | `JSONConfig` prefs, mirror list + latency/CDN memory, history, `ConfigWidget` |
| `workers.py` | 572 | `SearchWorker`, download worker threads, cover loading, signal fan-out |
| `ui.py` | 231 | `InterfaceAction` entry point: toolbar button, icon, version label |
| `hardcover.py` | 221 | Hardcover.app GraphQL client (shelves, lists, ISBNs) |
| `progress_delegate.py` | 123 | `QStyledItemDelegate`: smooth vector progress bars with MB/speed/ETA |
| `queue_manager.py` | 50 | `QueueManager(QObject)` — list wrapper emitting `queue_updated` |
| `__init__.py` | 33 | `LibgenDownloaderPlugin(InterfaceActionBase)` metadata + config hook |
| `calibre_dialog.ui` | — | Qt Designer form, loaded at runtime |

`test_plugin.py`, `test_search_logic.py`, `test_download_logic.py` existed with 9/9 offline tests passing as of commit `da31512`. They are **currently deleted in the working tree**. Restoring them requires a deliberate decision, not a blind `git checkout`.

### Backends (`config.py:BACKENDS`)

- `libgen` — classic HTML mirrors (default).
- `bookracy` — `api.bookracy.com`.
- `dual` — LibGen primary, Bookracy fallback (MD5 exact match → Title+Author+format).

Backend selection is a single pref `active_backend`. `get_active_backend()` / `set_active_backend()` are the only accessors.

### Import dual-mode pattern (every module, non-negotiable)

Calibre loads the zip as `calibre_plugins.libgen_store`, but local dev runs modules flat. Every module opens with a guarded dual import:

```python
try:
    from calibre_plugins.libgen_store.config import prefs
except ImportError:
    from config import prefs
```

Never collapse these to a single import — it breaks one of the two load paths.

---

## 5. Critical Boundaries & Safety Rules

1. **No external dependencies.** `bs4`, `lxml` (optional), `calibre.browser`, `qt.core` only. Never add `requests`, `pycurl`, or `PyQt*` directly.
2. **Dual-import pattern everywhere** (see §4). Silent `ImportError` fallbacks are the failure mode behind several past crash bugs.
3. **Anti-scraping invariants.** Cloudflare blocks requests without these — do not remove:
   - `Referer: https://<host>/` injected on every segment and single-stream request (fixes HTTP 503 hotlink blocks).
   - Per-segment User-Agent rotation + `Connection: keep-alive`.
   - Segment concurrency capped at 2–3; more triggers Cloudflare flood lockouts.
   - 512 KB chunk/reassembly buffers.
   - File concurrency default **1** (UI spinbox allows 1–4; higher splits bandwidth and invites rate limiting).
4. **Sandbox before import.** Downloads land in a sandbox directory. Library ingestion only happens through the Import Review Modal (Import All / Import Selected / Discard). Never auto-import mid-stream.
5. **Version stamping.** `config.py` holds `_BASE_VERSION_STR = "v1.70b"` and `_BUILD_COMMIT`. `make build` rewrites `_BUILD_COMMIT` with `git rev-list --count HEAD`. Beta version strings append the commit count (e.g. `v1.70b-155`).
6. **Beta isolation.** Beta builds, tags, and releases stay on `beta`. Never push, tag, or release without explicit instruction.
7. **No binaries in git.** `*.zip` and `releases/` are gitignored. Build artifacts are never committed.
8. **Multi-mirror behaviour**: "Auto (Best Latency)" — mirrors sorted by lowest latency, then cycled sequentially on failure. Latency and fastest-CDN scores persist in prefs.

---

## 6. Feature Surface (kept minimal)

- **Search**: field targeting, language/format filters, category partitions, bulk queue with deferral, retry dropdown.
- **Queue**: segmented views (Queued/Downloading/Downloaded/Failed), auto-prune, retry-failed, "Retry with Bookracy".
- **Mirrors**: latency-sorted cycling, dead-mirror discard, fastest-CDN rankings.
- **Library integration**: author search, Hardcover import with ISBN matching.
- **Easter eggs**: version-badge click toggles stats/cats.

---

## 7. Known Debt & Current Refactor

1. **`dialog.py` is a 3,821-line monolith.** Extraction is mid-flight: `QueueManager` (`queue_manager.py`) replaced raw `queue_items` lists, `workers.py` was split out of `dialog.py`. Continue this direction — new behaviour goes in its own module, not appended to `dialog.py`.
2. **No tests present.** The offline suite was deleted in the working tree. `make test` will fail until restored.
3. **Mirror drift is the main external risk.** LibGen domains change; `DEFAULT_FALLBACK_MIRRORS` and the mirror cache need periodic re-validation via `ping_mirrors.py`.
4. **Recent hot-fix cluster** (all in `git log`): missing-import crashes in `workers.py`/`dialog.py`, `queue_updated` signal firing before `setup_ui`, search parser dropping `detail_url`, collapsed-`colspan=5` Comics rows, `IndexError` in `on_item_progress`/`on_item_status`. When touching these paths, re-verify import completeness and signal ordering.

---

## 8. Knowledgebase & Docs

| File | Purpose |
|---|---|
| `README.md` | User-facing install/usage/features |
| `CHANGELOG.md` | Release notes (v1.50b → v1.0.0) |
| `INTERNAL_CHANGELOG.md` | Per-change log with `id / type / files / summary / why / validation` |
| `download-optimization-notes.md`, `search-optimization-notes.md` | Focused perf notes |
| `AGENTS.md` | Inherited machine rules + benchmark protocol |

Obsidian vault: `/home/thomas/Documents/tech/`
- Project tracker: `projects/project-calibre-libgen.md`
- Spec note: `calibre-libgen-store-plugin.md`

---

## 9. Handover Maintenance

Follow `AGENTS.md`. After meaningful changes:

1. Update `INTERNAL_CHANGELOG.md` with an `id / type / files / summary / why / validation` entry.
2. Update `CHANGELOG.md` when user-visible behaviour changes.
3. Update this `llm.md`: module line counts, commit state, backends, boundaries, known debt.
4. Write terse Obsidian notes under `/home/thomas/Documents/tech/` — kebab-case filenames, YAML `tags` + `date`, linked from `Tech Index.md` and `New-Dots Backlog.md`, with 1–2 horizontal cross-links to related notes.
5. Update `Dashboard.md` and `projects/project-calibre-libgen.md` when project status or metrics move.
6. Record resolved issues in the timeline file with attribution and running cumulative score.

Keep everything local. No external telemetry from benchmarks.