# Calibre LibGen Downloader (`calibre-lib`)

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/7sarus/calibre-lib?include_prereleases&color=blue)](https://github.com/7sarus/calibre-lib/releases)
[![Discord](https://img.shields.io/badge/Discord-Join%20Chat-5865F2?logo=discord&logoColor=white)](https://discord.gg/x2cZK7MT)
[![Reddit](https://img.shields.io/badge/Reddit-r%2Fbooksdev-FF4500?logo=reddit&logoColor=white)](https://reddit.com/r/booksdev)
[![GitHub stars](https://img.shields.io/github/stars/7sarus/calibre-lib?style=social)](https://github.com/7sarus/calibre-lib/stargazers)
[![GitHub all releases](https://img.shields.io/github/downloads/7sarus/calibre-lib/total)](https://github.com/7sarus/calibre-lib/releases)
[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-brightgreen.svg)](LICENSE)

A native **Calibre User Interface Action Plugin** that adds a dedicated **LibGen Downloader** button to Calibre's main toolbar.

Search books directly across Library Genesis mirrors, lock or filter by language and format (EPUB, PDF, MOBI, AZW3, etc.), queue multiple books into a **Bulk Download Queue**, and download them all together directly into your Calibre library.

---

## ✨ Features

- **Dedicated Toolbar Button & UI**: Adds a **LibGen** action button directly to Calibre's toolbar (`Ctrl+Shift+L` shortcut).
- **Field-Targeted Search**: Search specifically by **All Fields**, **Title**, **Author**, **Series**, **Publisher**, **Year**, or **ISBN**.
- **Mirror Latency & Bandwidth Benchmarking**:
  - Choose a specific mirror or leave on **Auto (Failover)**.
  - Dedicated **Mirrors & Health** tab: tests connection latency (TTFB `ms`) and live download bandwidth (`KB/s` / `MB/s`).
  - **Sort by Speed**: One-click sorting that reorders mirrors by bandwidth/latency and saves the fastest mirror as primary.
  - Set preferred mirrors as Primary manually or automatically.
- **Custom Mirrors**: Add, test, and persist your own custom LibGen mirror URLs directly from the UI.
- **Bulk Download Queue**:
  - Multi-row selection using standard click, `Ctrl+Click`, `Shift+Click`, or `Ctrl+A`.
  - Add to queue instantly with **`Ctrl+Shift+A`**, right-click **context menu**, or the bottom button.
  - Seamless workflow: focus remains in the search bar to keep queueing without tab switching.
  - Download all queued books in sequence with automatic **multi-mirror failover** across all active mirrors.
  - **Live Scrolling Activity Log**: Monospace terminal log embedded in the queue tab showing real-time network events, mirror failovers, and chunk streaming progress.
  - **Retry Failed Downloads**: One-click recovery button that re-queues and retries failed books against alternate mirrors.
  - Or click **Download Selected** for immediate one-click downloading.
- **Main Library Context Menu**: Right-click any book in Calibre's main library list to instantly **"Search LibGen for Author: <name>"**. Automatically launches search targeted to the Author field with clean filter resets.
- **Controlled Library Ingestion & Review**:
  - Downloads are decoupled into a sandbox directory and never forced into your Calibre library mid-stream.
  - Upon download completion or user abort ("Stop Download"), an **Import Review Modal** appears.
  - Review all downloaded files with options to **Import All**, **Import Selected**, or **Discard / Skip**.

- **Category Filtering (Fiction vs Sci-Tech / Academic)**:
  - Dedicated **Cat** selector: filter searches directly to **Fiction**, **Sci-Tech / Non-Fiction Books**, **Scientific Articles / Papers**, **Comics**, **Magazines**, or **All Categories**.
  - Targets LibGen's native `topics[]` database partitions.
- **Adaptive Working Mirror Memory**:
  - Automatically remembers the last mirror that successfully completed a search or download.
  - Prioritizes the proven working mirror first for all subsequent searches and download candidate URLs.
- **Language & Format Locking**:
  - Filter or lock to a preferred language (English, Spanish, French, German, Russian, etc.).
  - Filter or lock to a preferred format (EPUB, PDF, MOBI, AZW3, DJVU, CBR, CBZ).
  - Configurable filter modes:
    - **Prioritize**: Surfaces preferred language/format books at the top.
    - **Strict**: Only returns books matching the chosen criteria.
- **Zero External Dependencies**: Uses Calibre's bundled Python 3, Qt bindings (`qt.core`), and BeautifulSoup (`bs4`).

---

## 🚀 Installation

### Quick Install (Pre-built Release)

1. Download `libgen_downloader.zip` from the [Latest Release](https://github.com/7sarus/calibre-lib/releases).
2. Open **Calibre**.
3. Go to **Preferences** -> **Plugins** (under *Advanced*).
4. Click **Load plugin from file** and select `libgen_downloader.zip`.
5. Restart Calibre.

### Install from Source (Using Make)

```bash
git clone https://github.com/7sarus/calibre-lib.git
cd calibre-lib
make install
```

---

## 📖 Usage

1. Open **Calibre**.
2. Click the **LibGen** button on the main toolbar (or press `Ctrl+Shift+L`).
3. Type your search query and choose your preferred language and format.
4. From the search results:
   - Select rows using click, `Ctrl+Click`, or `Shift+Click`.
    - Press **`Ctrl+Shift+A`**, right-click and select **Add to Queue**, or click the bottom button. Focus automatically stays in the search box so you can keep searching and adding.
    - When ready, switch to the **Queue** tab and click **Start Bulk Download**.
    - Or click **Download Selected** to immediately download and import.
5. As books finish downloading, they will automatically appear in your Calibre library!


---

## ⚙️ Configuration

In Calibre, go to:
**Preferences** -> **Plugins** -> **User interface action plugins** -> select **LibGen Downloader** -> click **Customize plugin**.

Configure:
- **Primary Mirror URL**: Default `https://libgen.li`.
- **Fallback Mirrors**: Comma-separated list of fallback domains.
- **Connection Timeout**: Network timeout in seconds.
- **Lock / Preferred Language**: Default language preference.
- **Lock / Preferred Format**: Default format preference (EPUB, PDF, etc.).
- **Filter Enforcement**: `Prioritize` or `Strict`.
- **Max Results per Search**: Results count to retrieve.

---

## 🛠️ Development & Testing

- Build the `.zip` package:
  ```bash
  make build
  ```
- Run integration search & module tests in Calibre debug mode:
  ```bash
  make test
  ```
- Uninstall plugin:
  ```bash
  make uninstall
  ```

---

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=7sarus/calibre-lib&type=Date)](https://star-history.com/#7sarus/calibre-lib&Date)

---

## 🙏 Acknowledgements & Disclaimer

- **Upstream Origin**: This project is adapted and re-architected from [`obsfx/libgen-downloader`](https://github.com/obsfx/libgen-downloader) by Ömercan Balandı, translating its mirror handling and scraping concepts into a native Python/Qt Calibre plugin.
- **AI / LLM Assisted**: This rewrite was developed with the assistance of an LLM pair programmer.
- **For Fun**: This is strictly a "just for fun" experimental hobby project created for personal exploration and enjoyment.

## 💬 Community & Support

Join our community for discussions, feature requests, mirror health updates, and bug reports:  
- 💬 **Discord**: [Join the Discord Community](https://discord.gg/x2cZK7MT)
- 🤖 **Reddit**: [r/booksdev](https://reddit.com/r/booksdev)

---

## 📦 Releases & Version History

- **[v1.50 (Latest Release)](https://github.com/7sarus/calibre-lib/releases)**:
  - **Hardcover Reading Lists**: Sync "Want to Read" and custom shelves straight into your download queue with automatic duplicate detection.
  - **Search Existing Library Books**: Highlight books in Calibre and batch-search working mirrors without manual typing.
  - **Optimized Download Speeds**: 512 KB streaming buffers, smart connection limits, and automatic Cloudflare 503 bypasses for reliable transfers.
  - **Modernized UI & Live Metrics**: Real-time speed tiers, exact MB transferred, ETA countdowns, and movable tabs.
  - **Instant Mirror Failover**: Automatic fallback to fastest responsive mirrors with live latency indicators.
- **[v1.0.1 "Godzila" (Hotfix)](https://github.com/7sarus/calibre-lib/releases/tag/v1.0.1)**:
  - Fixed silent download and resolution failures across newer mirrors (`.li`, `.vg`, `.la`) due to anti-scraping checks.
  - Smooth animated cover preview text spinner (`⠋ 📖`) while covers load.
  - In-memory cover caching for zero-latency preview switching.
  - Natural cover aspect ratio preservation without image distortion.
  - Persistent queue across dialog sessions and prompt to preserve failed downloads on stop/error.
  - Multi-attribute deduplication using MD5, file size, and title metadata.
  - Prominent version badge in status bar (click 3x to toggle hidden download stats).
- **[v1.0.0 "Godzila"](https://github.com/7sarus/calibre-lib/releases/tag/v1.0.0)**:
  - Animated retro ASCII companion cat (`(=^.^=)`) in status bar reacting to search and download states.
  - Multi-threaded concurrent downloading (up to 3 simultaneous books) with live speed meters.
  - Embedded book cover preview pane for search results and queue.
  - Compact two-row search toolbar layout fitting small displays.
  - Multi-mirror failover and live scrolling activity log.
  - Retro ASCII progress bars inside queue table.
  - Controlled sandbox review modal before importing files into Calibre library.
- **[v0.2.0 "Batarang"](https://github.com/7sarus/calibre-lib/releases/tag/v0.2.0)**:
  - Live mirror bandwidth benchmarking (throughput alongside latency).
  - One-click "Sort by Speed" button with automatic primary mirror reordering.
  - Search field targeting (`Title`, `Author`, `Series`, `Publisher`, `Year`, `ISBN`).
  - Dedicated "Mirrors & Health" table with separate latency and speed columns.
  - Custom mirror add/remove with persistence.
- **[v0.1.0-alpha](https://github.com/7sarus/calibre-lib/releases/tag/v0.1.0-alpha)**:
  - Initial Calibre User Interface Action plugin port with bulk queue and library ingestion.

---

## 📜 License

[WTFPL](LICENSE)

