# LibGen Downloader (Calibre Plugin)

[![GitHub stars](https://img.shields.io/github/stars/7sarus/libgen-downloader?style=social)](https://github.com/7sarus/libgen-downloader/stargazers)
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

### Option 1: Using Make (Recommended)

Run:
```bash
make install
```

This packages `libgen_downloader.zip` and installs it via `calibre-customize -a libgen_downloader.zip`.

### Option 2: Manual Installation

1. Build the zip file:
   ```bash
   zip -q -r libgen_downloader.zip __init__.py ui.py dialog.py scraper.py config.py plugin-import-name-libgen_store.txt images/icon.png
   ```
2. Open **Calibre**.
3. Go to **Preferences** -> **Plugins** (under *Advanced*).
4. Click **Load plugin from file** and select `libgen_downloader.zip`.
5. Restart Calibre.

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

## 📜 License

[WTFPL](LICENSE)
