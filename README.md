# Calibre LibGen Downloader (`calibre-lib`)

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/7sarus/calibre-lib?include_prereleases&color=blue)](https://github.com/7sarus/calibre-lib/releases)
[![GitHub stars](https://img.shields.io/github/stars/7sarus/calibre-lib?style=social)](https://github.com/7sarus/calibre-lib/stargazers)
[![GitHub all releases](https://img.shields.io/github/downloads/7sarus/calibre-lib/total)](https://github.com/7sarus/calibre-lib/releases)
[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-brightgreen.svg)](LICENSE)

A native **Calibre User Interface Action Plugin** that adds a dedicated **LibGen Downloader** button to Calibre's main toolbar.

Search books directly across Library Genesis mirrors, lock or filter by language and format (EPUB, PDF, MOBI, AZW3, etc.), queue multiple books into a **Bulk Download Queue**, and download them all together directly into your Calibre library.

---

## ✨ Features

- **Dedicated Toolbar Button & UI**: Adds a **LibGen** action button directly to Calibre's toolbar (`Ctrl+Shift+L` shortcut).
- **Bulk Download Queue**:
  - Search books and select multiple titles using checkboxes.
  - Add selections to the **Bulk Queue** tab.
  - Download all queued books in sequence with live progress tracking.
  - Or click **Download Selected Now** for immediate one-click downloading.
- **Direct Calibre Library Integration**: Downloaded books are automatically ingested by Calibre's native library adder (`Add Books`), automatically parsing book metadata and covers into your library without opening a web browser.
- **Language & Format Locking**:
  - Filter or lock to a preferred language (English, Spanish, French, German, Russian, etc.).
  - Filter or lock to a preferred format (EPUB, PDF, MOBI, AZW3, DJVU, CBR, CBZ).
  - Configurable filter modes:
    - **Prioritize**: Surfaces preferred language/format books at the top.
    - **Strict**: Only returns books matching the chosen criteria.
- **Multi-Mirror Failover**: Automatically cycles through active LibGen mirrors (`libgen.li`, `libgen.vg`, `libgen.gl`, `libgen.bz`, `libgen.is`).
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
   - Check the boxes for the books you want, then click **Add Selected to Bulk Queue**.
   - Switch to the **Bulk Queue** tab and click **Start Bulk Download**.
   - Or click **Download Selected Now** to immediately download and import.
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

---

## 📜 License

[WTFPL](LICENSE)
