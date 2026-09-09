# LibGen Calibre Store Plugin

A native **Calibre Store Plugin** that integrates Library Genesis directly into Calibre's built-in **"Get Books"** interface.

Search books directly inside Calibre, lock or filter by language and format (EPUB, PDF, MOBI, etc.), and download books directly into your Calibre library with a single click.

---

## ✨ Features

- **Native Calibre Integration**: Subclasses `calibre.gui2.store.StorePlugin`, showing up directly in Calibre's **Get Books** search.
- **Language & Format Locking**:
  - Lock in a preferred language (e.g. English, Spanish, French, German, Russian, etc.).
  - Lock in a preferred format (e.g. EPUB, PDF, MOBI, AZW3, DJVU).
  - Configurable filter modes: **Strict** (hide non-matching files) or **Prioritize** (surface matching formats/languages at the top).
- **Multi-Mirror Failover**: Automatically cycles through active LibGen mirrors (`libgen.li`, `libgen.vg`, `libgen.gl`, `libgen.bz`, `libgen.la`, `libgen.is`) if a mirror is blocked or times out.
- **One-Click Download**: Automatically resolves authenticated direct download links and cover images during metadata lookup.
- **Zero External Dependencies**: Uses Calibre's bundled Python, Qt bindings (`qt.core`), and BeautifulSoup (`bs4`).

---

## 🚀 Installation

### Option 1: Using Make (Recommended)

Run:
```bash
make install
```

This packages `libgen_store.zip` and installs it via `calibre-customize -a libgen_store.zip`.

### Option 2: Manual Installation

1. Build the zip file:
   ```bash
   zip -q libgen_store.zip __init__.py store.py scraper.py config.py plugin-import-name.txt
   ```
2. Open **Calibre**.
3. Go to **Preferences** -> **Plugins** (under *Advanced*).
4. Click **Load plugin from file** and select `libgen_store.zip`.
5. Restart Calibre.

---

## ⚙️ Configuration

In Calibre, go to:
**Preferences** -> **Plugins** -> **Store Plugins** -> select **LibGen** -> click **Customize plugin**.

From the configuration dialog, you can configure:
- **Primary Mirror URL**: Default `https://libgen.li`.
- **Fallback Mirrors**: Comma-separated list of fallback domains.
- **Connection Timeout**: Network timeout in seconds.
- **Lock / Preferred Language**: Filter or prioritize books by language.
- **Lock / Preferred Format**: Filter or prioritize books by format (EPUB, PDF, MOBI, etc.).
- **Filter Enforcement**:
  - `Prioritize`: Surfaces matching language/format books at the top of search results.
  - `Strict`: Only returns books matching your chosen language and format.
- **Max Results per Search**: Results count to retrieve.

---

## 📖 Usage

1. Open Calibre.
2. Click **Get Books** in the main toolbar.
3. In the left panel under **Stores**, ensure **LibGen** is checked.
4. Type your search query (Title, Author, or ISBN) and click **Search**.
5. Right-click any result to:
   - Click **Download** to download the book directly into your Calibre library.
   - Click **Open Store** to view the book's detail page in your browser.

---

## 🛠️ Development & Testing

- Build the `.zip` package:
  ```bash
  make build
  ```
- Run integration search test in Calibre debug mode:
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
