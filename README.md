# MangaReader – hentai20.io Desktop Client

A compact, ad-free, dark-mode Windows manga reader built with Python + CustomTkinter.

![Screenshot1](https://github.com/ilickft/Freaker/raw/main/screenshots/screenshot1.png)

## Features
- Home grid: 40 covers per page, paginated, with search
- Manga detail: chapter list with dates, sorted newest-first
- Chapter reader: vertical scroll, lazy image loading (3 ahead)
- One-click chapter download → `~/MangaReader Downloads/<manga>/<chapter>/001.jpg …`
- Progress bar during downloads; graceful error popups

## Project Structure

```
mangareader/
├── main.py               ← PyInstaller entry point
├── mangareader.spec      ← PyInstaller spec (single .exe)
├── requirements.txt
└── src/
    ├── scraper.py        ← All network + HTML parsing (no UI)
    ├── downloader.py     ← Chapter download logic (background thread)
    ├── image_cache.py    ← Thread-safe LRU PIL image cache
    └── app.py            ← Full CustomTkinter UI
```

## Run from source

```bash
# 1. Create venv (recommended)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# 2. Install deps
pip install -r requirements.txt

# 3. Run
python main.py
```

## Build single Windows executable

```bash
pip install pyinstaller
pyinstaller mangareader.spec
```

Output: `dist\MangaReader.exe` — fully self-contained, no console window.

### Optional: smaller binary
Install UPX (https://upx.github.io/) and add it to PATH before running PyInstaller.
Typical size: ~35–50 MB before UPX, ~20–30 MB after.

### One-liner alternative (no spec file)

```bash
pyinstaller --onefile --windowed --name MangaReader ^
  --hidden-import customtkinter ^
  --hidden-import PIL._tkinter_finder ^
  --collect-data customtkinter ^
  --paths src ^
  main.py
```

## Scraping notes

| Page type     | Selector / method                             |
|---------------|-----------------------------------------------|
| Home grid     | `.bsx a` → href, img[src], `.tt`, `.epxs`    |
| Pagination    | `https://hentai20.io/page/{n}/`               |
| Search        | `https://hentai20.io/?s=<query>`              |
| Manga detail  | `#chapterlist .eph-num a` for chapter list    |
| Chapter imgs  | `ts_reader.run({…})` JSON in `<script>` tag  |
| Fallback imgs | `#readerarea img[src]`                        |
