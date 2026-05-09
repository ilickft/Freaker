"""
app.py – Main CustomTkinter application for MangaReader (hentai20.io)
Modular: Home grid → Manga detail → Chapter reader, plus Downloads manager.
"""

import os
import sys
import queue
import shutil
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image, ImageTk

# Adjust sys.path when running as PyInstaller bundle
if getattr(sys, "frozen", False):
    _HERE = Path(sys._MEIPASS)
    sys.path.insert(0, str(_HERE))

import scraper
import downloader
from image_cache import ImageCache

# ── Theme ──────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

ACCENT       = "#e63946"
BG_DARK      = "#0d0d0d"
BG_MID       = "#181818"
BG_CARD      = "#1e1e1e"
BG_SIDEBAR   = "#111111"
TEXT_PRIMARY = "#f0f0f0"
TEXT_MUTED   = "#888888"
TEXT_ACCENT  = ACCENT

THUMB_W, THUMB_H = 160, 230
COLS        = 5  # cards per row
SIDEBAR_W   = 160
READER_IMG_W = 720


# ══════════════════════════════════════════════════════════════════════════════
# Helper widgets
# ══════════════════════════════════════════════════════════════════════════════

class ScrollableFrame(ctk.CTkScrollableFrame):
    """A thin wrapper so we can set fg_color uniformly."""
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", BG_DARK)
        kw.setdefault("scrollbar_button_color", "#333")
        kw.setdefault("scrollbar_button_hover_color", ACCENT)
        super().__init__(master, **kw)


class SidebarButton(ctk.CTkButton):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", "transparent")
        kw.setdefault("hover_color", "#2a2a2a")
        kw.setdefault("text_color", TEXT_PRIMARY)
        kw.setdefault("anchor", "w")
        kw.setdefault("corner_radius", 6)
        kw.setdefault("height", 38)
        kw.setdefault("font", ctk.CTkFont(size=13))
        super().__init__(master, **kw)


class AccentButton(ctk.CTkButton):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", ACCENT)
        kw.setdefault("hover_color", "#b5000f")
        kw.setdefault("text_color", "#ffffff")
        kw.setdefault("corner_radius", 6)
        kw.setdefault("font", ctk.CTkFont(size=12, weight="bold"))
        super().__init__(master, **kw)


class GhostButton(ctk.CTkButton):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", "#2a2a2a")
        kw.setdefault("hover_color", "#383838")
        kw.setdefault("text_color", TEXT_PRIMARY)
        kw.setdefault("corner_radius", 6)
        kw.setdefault("font", ctk.CTkFont(size=12))
        super().__init__(master, **kw)


def error_popup(title: str, message: str) -> None:
    win = ctk.CTkToplevel()
    win.title(title)
    win.resizable(False, False)
    win.configure(fg_color=BG_MID)
    win.grab_set()
    ctk.CTkLabel(win, text=f"⚠  {message}", text_color=TEXT_PRIMARY,
                 font=ctk.CTkFont(size=13), wraplength=320).pack(padx=24, pady=(24, 12))
    ctk.CTkButton(win, text="OK", fg_color=ACCENT, hover_color="#b5000f",
                  command=win.destroy, width=80).pack(pady=(0, 20))
    win.after(100, win.lift)


# ══════════════════════════════════════════════════════════════════════════════
# Home view (grid of manga cards)
# ══════════════════════════════════════════════════════════════════════════════

class HomeView(ctk.CTkFrame):
    def __init__(self, master, app, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._page = 1
        self._loading = False
        self._manga_list: list[dict] = []
        self._tk_images: dict[str, ImageTk.PhotoImage] = {}

        self._build_topbar()
        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self._grid = self._scroll  # cards go here

        self._build_pagination()
        self.load_page(1)

    # ── layout ──────────────────────────────────────────────

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        ctk.CTkLabel(bar, text="Browse", font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left", padx=16)

        self._search_var = ctk.StringVar()
        entry = ctk.CTkEntry(bar, placeholder_text="Search manga…",
                             textvariable=self._search_var,
                             width=240, fg_color="#262626", border_color="#333",
                             text_color=TEXT_PRIMARY)
        entry.pack(side="right", padx=8, pady=8)
        entry.bind("<Return>", lambda _: self._do_search())
        
        AccentButton(bar, text="Search", width=72,
                     command=self._do_search).pack(side="right", padx=(0, 4), pady=8)
        
        GhostButton(bar, text="↻ Refresh", width=90,
                    command=lambda: self.load_page(self._page)).pack(side="right", padx=4, pady=8)

    def _build_pagination(self):
        self._pag_frame = ctk.CTkFrame(self, fg_color=BG_MID, height=48, corner_radius=0)
        self._pag_frame.pack(fill="x", side="bottom")
        self._pag_frame.pack_propagate(False)

        self._prev_btn = GhostButton(self._pag_frame, text="◀  Prev", width=90,
                                     command=self._prev_page)
        self._prev_btn.pack(side="left", padx=12, pady=8)

        self._page_label = ctk.CTkLabel(self._pag_frame, text="Page 1",
                                        font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self._page_label.pack(side="left", padx=8)

        GhostButton(self._pag_frame, text="Next  ▶", width=90,
                    command=self._next_page).pack(side="left", padx=4, pady=8)

        self._status_label = ctk.CTkLabel(self._pag_frame, text="",
                                          font=ctk.CTkFont(size=11),
                                          text_color=TEXT_MUTED)
        self._status_label.pack(side="right", padx=16)

    # ── loading ──────────────────────────────────────────────

    def load_page(self, page: int, results: Optional[list[dict]] = None):
        if self._loading:
            return
        self._loading = True
        self._page = page
        self._page_label.configure(text=f"Page {page}")
        self._prev_btn.configure(state="disabled" if page == 1 else "normal")
        self._status_label.configure(text="Loading…")
        self._clear_grid()

        if results is not None:
            self._loading = False
            self._render_cards(results)
            return

        threading.Thread(target=self._fetch_thread, args=(page,), daemon=True).start()

    def _fetch_thread(self, page: int):
        try:
            data = scraper.fetch_home(page)
            self.after(0, self._on_fetched, data)
        except Exception as exc:
            self.after(0, error_popup, "Network Error", str(exc))
            self.after(0, lambda: self._status_label.configure(text="Error"))
            self._loading = False

    def _on_fetched(self, data: list[dict]):
        self._loading = False
        self._manga_list = data
        self._render_cards(data)
        self._status_label.configure(text=f"{len(data)} titles")

    def _do_search(self):
        q = self._search_var.get().strip()
        if not q:
            self.load_page(1)
            return
        self._loading = True
        self._status_label.configure(text="Searching…")
        self._clear_grid()
        threading.Thread(target=self._search_thread, args=(q,), daemon=True).start()

    def _search_thread(self, q: str):
        try:
            data = scraper.search_manga(q)
            self.after(0, self._on_fetched, data)
        except Exception as exc:
            self.after(0, error_popup, "Search Error", str(exc))
            self._loading = False

    # ── grid rendering ───────────────────────────────────────

    def _clear_grid(self):
        for w in self._grid.winfo_children():
            w.destroy()
        self._tk_images.clear()

    def _render_cards(self, items: list[dict]):
        for i, item in enumerate(items):
            row, col = divmod(i, COLS)
            card = self._make_card(item)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="n")

        # Load thumbnails asynchronously
        for item in items:
            if item["thumb"]:
                self._app.img_cache.get_thumb(
                    item["thumb"],
                    (THUMB_W, THUMB_H),
                    lambda url, tk_img: self._set_thumb(url, tk_img),
                )

    def _make_card(self, item: dict) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._grid, fg_color=BG_CARD, corner_radius=8,
                            width=THUMB_W, cursor="hand2")
        card.grid_propagate(False)

        # Placeholder image label
        ph = Image.new("RGB", (THUMB_W, THUMB_H), (28, 28, 28))
        tk_ph = ImageTk.PhotoImage(ph)
        self._tk_images[item["thumb"] + "_ph"] = tk_ph

        img_lbl = ctk.CTkLabel(card, image=tk_ph, text="",
                                width=THUMB_W, height=THUMB_H)
        img_lbl.image_ref = tk_ph
        img_lbl.pack()
        img_lbl._manga_url = item["url"]

        # Store reference so we can swap when thumb arrives
        if item["thumb"]:
            self._tk_images[item["thumb"] + "_lbl"] = img_lbl  # type: ignore

        title_lbl = ctk.CTkLabel(card, text=item["title"], wraplength=THUMB_W - 8,
                                  font=ctk.CTkFont(size=10, weight="bold"),
                                  text_color=TEXT_PRIMARY,
                                  justify="center")
        title_lbl.pack(padx=4, pady=(2, 0))

        ch_lbl = ctk.CTkLabel(card, text=item.get("latest_chapter", ""),
                               font=ctk.CTkFont(size=9), text_color=TEXT_MUTED)
        ch_lbl.pack(pady=(0, 4))

        # Click anywhere on card → open manga
        for widget in (card, img_lbl, title_lbl, ch_lbl):
            widget.bind("<Button-1>", lambda _, u=item["url"]: self._app.open_manga(u))

        return card

    def _set_thumb(self, url: str, tk_img: ImageTk.PhotoImage):
        key = url + "_lbl"
        lbl = self._tk_images.get(key)
        if lbl and lbl.winfo_exists():
            lbl.configure(image=tk_img)
            lbl.image_ref = tk_img
        self._tk_images[url] = tk_img

    # ── pagination ───────────────────────────────────────────

    def _next_page(self):
        self.load_page(self._page + 1)

    def _prev_page(self):
        if self._page > 1:
            self.load_page(self._page - 1)


# ══════════════════════════════════════════════════════════════════════════════
# Manga detail view (cover + chapter list)
# ══════════════════════════════════════════════════════════════════════════════

class MangaDetailView(ctk.CTkFrame):
    def __init__(self, master, app, manga_url: str, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._manga_url = manga_url
        self._manga_data: Optional[dict] = None
        self._cover_ref: Optional[ImageTk.PhotoImage] = None

        self._build_topbar()

        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True)

        self._content = ctk.CTkFrame(self._scroll, fg_color=BG_DARK)
        self._content.pack(fill="both", expand=True, padx=16, pady=12)

        self._show_spinner()
        threading.Thread(target=self._fetch_detail, daemon=True).start()

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        GhostButton(bar, text="◀  Back", width=80,
                    command=self._app.go_home).pack(side="left", padx=12, pady=8)
        self._title_lbl = ctk.CTkLabel(bar, text="Loading…",
                                        font=ctk.CTkFont(size=15, weight="bold"),
                                        text_color=TEXT_PRIMARY)
        self._title_lbl.pack(side="left", padx=8)

    def _show_spinner(self):
        ctk.CTkLabel(self._content, text="Loading manga details…",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(pady=40)

    def _fetch_detail(self):
        try:
            data = scraper.fetch_manga_detail(self._manga_url)
            self.after(0, self._render, data)
        except Exception as exc:
            self.after(0, error_popup, "Error", str(exc))

    def _render(self, data: dict):
        self._manga_data = data
        for w in self._content.winfo_children():
            w.destroy()

        self._title_lbl.configure(text=data["title"])

        # ── Header row: cover + info ────────────────────────
        header = ctk.CTkFrame(self._content, fg_color=BG_DARK)
        header.pack(fill="x", pady=(0, 12))

        # Cover
        cover_frame = ctk.CTkFrame(header, fg_color=BG_CARD, corner_radius=8,
                                    width=150, height=215)
        cover_frame.pack(side="left", padx=(0, 16))
        cover_frame.pack_propagate(False)

        ph = Image.new("RGB", (150, 215), (28, 28, 28))
        self._cover_ref = ImageTk.PhotoImage(ph)
        self._cover_lbl = ctk.CTkLabel(cover_frame, image=self._cover_ref, text="",
                                        width=150, height=215)
        self._cover_lbl.pack()

        if data["cover"]:
            self._app.img_cache.get_thumb(data["cover"], (150, 215), self._set_cover)

        # Info panel
        info = ctk.CTkFrame(header, fg_color=BG_DARK)
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(info, text=data["title"],
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXT_PRIMARY, wraplength=420,
                     justify="left").pack(anchor="w")

        if data["status"]:
            ctk.CTkLabel(info, text=f"Status: {data['status']}",
                         font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(anchor="w", pady=2)

        if data["genres"]:
            ctk.CTkLabel(info, text="Genres: " + ", ".join(data["genres"]),
                         font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
                         wraplength=420, justify="left").pack(anchor="w", pady=2)

        if data["synopsis"]:
            ctk.CTkLabel(info, text=data["synopsis"],
                         font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
                         wraplength=420, justify="left").pack(anchor="w", pady=(8, 0))

        # ── Chapter list ────────────────────────────────────
        ctk.CTkLabel(self._content,
                     text=f"Chapters ({len(data['chapters'])})",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(anchor="w", pady=(8, 4))

        sep = ctk.CTkFrame(self._content, fg_color="#2a2a2a", height=1)
        sep.pack(fill="x", pady=(0, 6))

        for ch in data["chapters"]:
            self._make_chapter_row(ch, data["title"])

    def _make_chapter_row(self, ch: dict, manga_title: str):
        row = ctk.CTkFrame(self._content, fg_color=BG_CARD, corner_radius=6, height=40)
        row.pack(fill="x", pady=2)
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=ch["title"],
                     font=ctk.CTkFont(size=12), text_color=TEXT_PRIMARY,
                     anchor="w").pack(side="left", padx=12, pady=0)
        ctk.CTkLabel(row, text=ch.get("date", ""),
                     font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(side="left", padx=4)

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right", padx=8, pady=5)

        AccentButton(btn_frame, text="Read", width=64, height=28,
                     command=lambda u=ch["url"], t=ch["title"]:
                         self._app.open_reader(u, manga_title, t)
                     ).pack(side="left", padx=2)

    def _set_cover(self, url: str, tk_img: ImageTk.PhotoImage):
        self._cover_ref = tk_img
        if self._cover_lbl.winfo_exists():
            self._cover_lbl.configure(image=tk_img)


# ══════════════════════════════════════════════════════════════════════════════
# Chapter reader view
# ══════════════════════════════════════════════════════════════════════════════

class ReaderView(ctk.CTkFrame):
    def __init__(self, master, app, chapter_url: str,
                 manga_title: str, chapter_title: str, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._chapter_url = chapter_url
        self._manga_title = manga_title
        self._chapter_title = chapter_title
        self._image_urls: list[str] = []
        self._tk_images: dict[str, ImageTk.PhotoImage] = {}
        self._img_labels: dict[str, ctk.CTkLabel] = {}
        self._prev_url = ""
        self._next_url = ""
        self._dl_thread: Optional[threading.Thread] = None
        self._dl_stop = threading.Event()

        self._build_topbar()

        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True)

        self._canvas_col = ctk.CTkFrame(self._scroll, fg_color=BG_DARK)
        self._canvas_col.pack(anchor="center")

        self._show_spinner()
        threading.Thread(target=self._fetch_chapter, daemon=True).start()

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        GhostButton(bar, text="◀  Back", width=80,
                    command=self._app.go_back).pack(side="left", padx=8, pady=8)

        ctk.CTkLabel(bar, text=self._chapter_title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left", padx=8)

        # Download section (right)
        self._dl_bar_var = ctk.DoubleVar(value=0)
        self._dl_progress = ctk.CTkProgressBar(bar, variable=self._dl_bar_var,
                                                width=160, height=8,
                                                fg_color="#333", progress_color=ACCENT)
        self._dl_label = ctk.CTkLabel(bar, text="", font=ctk.CTkFont(size=10),
                                       text_color=TEXT_MUTED)
        self._dl_btn = AccentButton(bar, text="⬇  Download", width=120, height=32,
                                    command=self._start_download)
        self._dl_btn.pack(side="right", padx=12, pady=10)

    def _scroll_down(self, event=None):
        if hasattr(self._scroll, "_parent_canvas"):
            self._scroll._parent_canvas.yview_scroll(1, "pages")

    def _show_spinner(self):
        ctk.CTkLabel(self._canvas_col, text="Fetching chapter images…",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(pady=40)

    def _fetch_chapter(self):
        try:
            data = scraper.fetch_chapter_images(self._chapter_url)
            self.after(0, self._render, data)
        except Exception as exc:
            self.after(0, error_popup, "Load Error", str(exc))

    def _render(self, data: dict):
        self._image_urls = data["images"]
        self._prev_url = data["prev_url"]
        self._next_url = data["next_url"]

        for w in self._canvas_col.winfo_children():
            w.destroy()

        if not self._image_urls:
            ctk.CTkLabel(self._canvas_col, text="No images found.",
                         text_color=ACCENT).pack(pady=40)
            return

        # Build image labels with placeholders
        for url in self._image_urls:
            ph = Image.new("RGB", (READER_IMG_W, int(READER_IMG_W * 1.5)), (18, 18, 18))
            tk_ph = ImageTk.PhotoImage(ph)
            lbl = ctk.CTkLabel(self._canvas_col, image=tk_ph, text="",
                                width=READER_IMG_W)
            lbl.image_ref = tk_ph
            lbl.pack(pady=1)
            lbl.bind("<Button-1>", self._scroll_down)
            self._img_labels[url] = lbl

        # Lazy-load: fetch first 3 immediately, rest on idle
        self._load_batch(self._image_urls[:3])
        if len(self._image_urls) > 3:
            self.after(200, lambda: self._load_batch(self._image_urls[3:]))

    def _load_batch(self, urls: list[str]):
        for url in urls:
            self._app.img_cache.get_reader_image(url, READER_IMG_W, self._set_image)

    def _set_image(self, url: str, tk_img: ImageTk.PhotoImage):
        self._tk_images[url] = tk_img
        lbl = self._img_labels.get(url)
        if lbl and lbl.winfo_exists():
            lbl.configure(image=tk_img, height=tk_img.height())
            lbl.image_ref = tk_img

    # ── Download ──────────────────────────────────────────────

    def _start_download(self):
        if self._dl_thread and self._dl_thread.is_alive():
            return

        self._dl_stop.clear()
        self._dl_btn.configure(state="disabled", text="Downloading…")
        self._dl_bar_var.set(0)
        self._dl_progress.pack(side="right", padx=4)
        self._dl_label.pack(side="right")

        self._dl_thread, _ = downloader.start_download_thread(
            chapter_url=self._chapter_url,
            manga_title=self._manga_title,
            chapter_title=self._chapter_title,
            on_progress=self._on_dl_progress,
            on_done=self._on_dl_done,
            on_error=self._on_dl_error,
            stop_event=self._dl_stop,
        )

    def _on_dl_progress(self, current: int, total: int):
        def _update():
            pct = current / total if total else 0
            self._dl_bar_var.set(pct)
            self._dl_label.configure(text=f"{current}/{total}")
        self.after(0, _update)

    def _on_dl_done(self, dest: str):
        def _done():
            self._dl_btn.configure(state="normal", text="✓ Saved")
            self._dl_label.configure(text=dest, text_color=TEXT_MUTED)
            self._dl_progress.pack_forget()
        self.after(0, _done)

    def _on_dl_error(self, msg: str):
        def _err():
            self._dl_btn.configure(state="normal", text="⬇  Download")
            self._dl_progress.pack_forget()
            self._dl_label.pack_forget()
            error_popup("Download Error", msg)
        self.after(0, _err)


# ══════════════════════════════════════════════════════════════════════════════
# Offline Chapter reader view
# ══════════════════════════════════════════════════════════════════════════════

class OfflineReaderView(ctk.CTkFrame):
    def __init__(self, master, app, chapter_path: Path,
                 manga_title: str, chapter_title: str, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._path = chapter_path
        self._manga_title = manga_title
        self._chapter_title = chapter_title
        self._image_paths: list[Path] = []
        self._tk_images: dict[str, ImageTk.PhotoImage] = {}
        self._img_labels: dict[str, ctk.CTkLabel] = {}

        self._build_topbar()

        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True)

        self._canvas_col = ctk.CTkFrame(self._scroll, fg_color=BG_DARK)
        self._canvas_col.pack(anchor="center")

        self._load_local_chapter()

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        GhostButton(bar, text="◀  Back", width=80,
                    command=self._app.go_back).pack(side="left", padx=8, pady=8)

        ctk.CTkLabel(bar, text=f"[OFFLINE] {self._chapter_title}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left", padx=8)

    def _scroll_down(self, event=None):
        if hasattr(self._scroll, "_parent_canvas"):
            self._scroll._parent_canvas.yview_scroll(1, "pages")

    def _load_local_chapter(self):
        if not self._path.exists():
            ctk.CTkLabel(self._canvas_col, text="Folder not found.",
                         text_color=ACCENT).pack(pady=40)
            return

        self._image_paths = sorted([
            p for p in self._path.iterdir()
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        ])

        if not self._image_paths:
            ctk.CTkLabel(self._canvas_col, text="No images found in folder.",
                         text_color=ACCENT).pack(pady=40)
            return

        for p in self._image_paths:
            # Simple placeholder while loading
            ph = Image.new("RGB", (READER_IMG_W, int(READER_IMG_W * 1.5)), (18, 18, 18))
            tk_ph = ImageTk.PhotoImage(ph)
            lbl = ctk.CTkLabel(self._canvas_col, image=tk_ph, text="", width=READER_IMG_W)
            lbl.image_ref = tk_ph
            lbl.pack(pady=1)
            lbl.bind("<Button-1>", self._scroll_down)
            self._img_labels[str(p)] = lbl

        # Load first few, then rest on idle
        self._load_batch(self._image_paths[:3])
        if len(self._image_paths) > 3:
            self.after(200, lambda: self._load_batch(self._image_paths[3:]))

    def _load_batch(self, paths: list[Path]):
        for p in paths:
            threading.Thread(target=self._load_one, args=(p,), daemon=True).start()

    def _load_one(self, path: Path):
        try:
            img = Image.open(path).convert("RGB")
            # Reuse scaling logic if possible, or just do it here
            if img.width > READER_IMG_W:
                ratio = READER_IMG_W / img.width
                new_h = int(img.height * ratio)
                img = img.resize((READER_IMG_W, new_h), Image.LANCZOS)
            
            tk_img = ImageTk.PhotoImage(img)
            self.after(0, self._set_image, str(path), tk_img)
        except Exception:
            pass

    def _set_image(self, path_str: str, tk_img: ImageTk.PhotoImage):
        self._tk_images[path_str] = tk_img
        lbl = self._img_labels.get(path_str)
        if lbl and lbl.winfo_exists():
            lbl.configure(image=tk_img, height=tk_img.height())
            lbl.image_ref = tk_img


# ══════════════════════════════════════════════════════════════════════════════
# Downloads manager view
# ══════════════════════════════════════════════════════════════════════════════

class DownloadsView(ctk.CTkFrame):
    def __init__(self, master, app, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._build()

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="Downloads",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left", padx=16)
        AccentButton(bar, text="↻  Refresh", width=90,
                     command=self._refresh).pack(side="right", padx=12, pady=8)

        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True)
        self._content = self._scroll
        self._refresh()

    def _refresh(self):
        for w in self._content.winfo_children():
            w.destroy()

        root = downloader.DEFAULT_DOWNLOAD_ROOT
        if not root.exists():
            ctk.CTkLabel(self._content, text="No downloads yet.",
                         text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        manga_dirs = sorted(root.iterdir()) if root.is_dir() else []
        if not manga_dirs:
            ctk.CTkLabel(self._content, text="No downloads yet.",
                         text_color=TEXT_MUTED).pack(pady=40)
            return

        for manga_dir in manga_dirs:
            if not manga_dir.is_dir():
                continue
            header = ctk.CTkFrame(self._content, fg_color=BG_MID, corner_radius=6, height=36)
            header.pack(fill="x", padx=8, pady=(8, 2))
            header.pack_propagate(False)
            ctk.CTkLabel(header, text=manga_dir.name,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=TEXT_PRIMARY).pack(side="left", padx=12)

            for ch_dir in sorted(manga_dir.iterdir()):
                if not ch_dir.is_dir():
                    continue
                imgs = list(ch_dir.glob("*.jpg")) + list(ch_dir.glob("*.png")) \
                     + list(ch_dir.glob("*.webp"))
                row = ctk.CTkFrame(self._content, fg_color=BG_CARD, corner_radius=4, height=34)
                row.pack(fill="x", padx=24, pady=1)
                row.pack_propagate(False)

                ctk.CTkLabel(row, text=f"  {ch_dir.name}",
                             font=ctk.CTkFont(size=11), text_color=TEXT_PRIMARY,
                             anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"{len(imgs)} pages",
                             font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(side="left",
                                                                                      padx=8)

                btn_frame = ctk.CTkFrame(row, fg_color="transparent")
                btn_frame.pack(side="right", padx=8)

                AccentButton(btn_frame, text="Read", width=64, height=24,
                            command=lambda p=ch_dir, m=manga_dir.name, c=ch_dir.name: 
                                self._app.open_offline_reader(p, m, c)
                            ).pack(side="left", padx=2)

                GhostButton(btn_frame, text="Delete", width=64, height=24,
                            command=lambda p=ch_dir: self._delete_chapter(p)
                            ).pack(side="left", padx=2)

    def _delete_chapter(self, path: Path):
        try:
            shutil.rmtree(path)
            # If manga folder is empty, delete it too
            manga_dir = path.parent
            if not any(manga_dir.iterdir()):
                shutil.rmtree(manga_dir)
            self._refresh()
        except Exception as e:
            error_popup("Error", f"Could not delete: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Offline Library View (Grid of downloaded mangas)
# ══════════════════════════════════════════════════════════════════════════════

class OfflineLibraryView(ctk.CTkFrame):
    def __init__(self, master, app, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._tk_images: dict[str, ImageTk.PhotoImage] = {}
        self._build()

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="Library (Offline)",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left", padx=16)
        
        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True)
        self._grid = self._scroll
        self._refresh()

    def _refresh(self):
        for w in self._grid.winfo_children():
            w.destroy()
        self._tk_images.clear()

        root = downloader.DEFAULT_DOWNLOAD_ROOT
        if not root.exists() or not root.is_dir():
            ctk.CTkLabel(self._grid, text="No downloads yet.",
                         text_color=TEXT_MUTED, font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        manga_dirs = sorted([d for d in root.iterdir() if d.is_dir()])
        if not manga_dirs:
            ctk.CTkLabel(self._grid, text="No downloads yet.",
                         text_color=TEXT_MUTED).pack(pady=40)
            return

        for i, m_dir in enumerate(manga_dirs):
            row, col = divmod(i, COLS)
            card = self._make_card(m_dir)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="n")

    def _make_card(self, m_dir: Path) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._grid, fg_color=BG_CARD, corner_radius=8,
                            width=THUMB_W, cursor="hand2")
        card.grid_propagate(False)

        # Thumbnail logic: find first image in first chapter
        thumb_path = self._find_thumbnail(m_dir)
        
        ph = Image.new("RGB", (THUMB_W, THUMB_H), (28, 28, 28))
        tk_img = ImageTk.PhotoImage(ph)
        
        if thumb_path:
            try:
                img = Image.open(thumb_path).convert("RGB")
                # Fit logic
                img.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
                canvas = Image.new("RGB", (THUMB_W, THUMB_H), (20, 20, 20))
                x = (THUMB_W - img.width) // 2
                y = (THUMB_H - img.height) // 2
                canvas.paste(img, (x, y))
                tk_img = ImageTk.PhotoImage(canvas)
            except Exception:
                pass

        self._tk_images[str(m_dir)] = tk_img
        img_lbl = ctk.CTkLabel(card, image=tk_img, text="", width=THUMB_W, height=THUMB_H)
        img_lbl.pack()

        title_lbl = ctk.CTkLabel(card, text=m_dir.name, wraplength=THUMB_W - 8,
                                  font=ctk.CTkFont(size=10, weight="bold"),
                                  text_color=TEXT_PRIMARY, justify="center")
        title_lbl.pack(padx=4, pady=(4, 4))

        for widget in (card, img_lbl, title_lbl):
            widget.bind("<Button-1>", lambda _, p=m_dir: self._app.open_offline_manga(p))

        return card

    def _find_thumbnail(self, m_dir: Path) -> Optional[Path]:
        # Try to find an image in any subfolder
        for ch_dir in sorted(m_dir.iterdir()):
            if ch_dir.is_dir():
                imgs = sorted([p for p in ch_dir.iterdir() if p.suffix.lower() in (".jpg", ".png", ".webp")])
                if imgs:
                    return imgs[0]
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Offline Manga Detail View
# ══════════════════════════════════════════════════════════════════════════════

class OfflineMangaDetailView(ctk.CTkFrame):
    def __init__(self, master, app, manga_path: Path, **kw):
        kw.setdefault("fg_color", BG_DARK)
        super().__init__(master, **kw)
        self._app = app
        self._path = manga_path
        self._build()

    def _build(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=54, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        GhostButton(bar, text="◀  Back", width=80,
                    command=self._app.go_library).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(bar, text=self._path.name,
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT_PRIMARY).pack(side="left", padx=8)

        self._scroll = ScrollableFrame(self, fg_color=BG_DARK)
        self._scroll.pack(fill="both", expand=True)
        self._content = self._scroll
        self._refresh()

    def _refresh(self):
        for w in self._content.winfo_children():
            w.destroy()

        if not self._path.exists():
            self._app.go_library()
            return

        ch_dirs = sorted([d for d in self._path.iterdir() if d.is_dir()])
        if not ch_dirs:
            ctk.CTkLabel(self._content, text="No chapters found.",
                         text_color=TEXT_MUTED).pack(pady=40)
            return

        for ch_dir in ch_dirs:
            imgs = [p for p in ch_dir.iterdir() if p.suffix.lower() in (".jpg", ".png", ".webp")]
            
            row = ctk.CTkFrame(self._content, fg_color=BG_CARD, corner_radius=6, height=44)
            row.pack(fill="x", padx=16, pady=2)
            row.pack_propagate(False)

            ctk.CTkLabel(row, text=ch_dir.name, font=ctk.CTkFont(size=12),
                         text_color=TEXT_PRIMARY, anchor="w").pack(side="left", padx=12)
            ctk.CTkLabel(row, text=f"{len(imgs)} pages", font=ctk.CTkFont(size=10),
                         text_color=TEXT_MUTED).pack(side="left", padx=8)

            btn_frame = ctk.CTkFrame(row, fg_color="transparent")
            btn_frame.pack(side="right", padx=8)

            AccentButton(btn_frame, text="Read", width=64, height=28,
                         command=lambda p=ch_dir: self._app.open_offline_reader(p, self._path.name, p.name)
                         ).pack(side="left", padx=2)
            
            GhostButton(btn_frame, text="Delete", width=64, height=28,
                        command=lambda p=ch_dir: self._delete_chapter(p)
                        ).pack(side="left", padx=2)

    def _delete_chapter(self, path: Path):
        try:
            shutil.rmtree(path)
            # If manga folder is empty, delete it too and go back
            manga_dir = path.parent
            if not any(manga_dir.iterdir()):
                shutil.rmtree(manga_dir)
                self._app.go_library()
            else:
                self._refresh()
        except Exception as e:
            error_popup("Error", f"Could not delete: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Root application window
# ══════════════════════════════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MangaReader – hentai20.io")
        self.geometry("1100x700")
        self.minsize(900, 600)
        self.configure(fg_color=BG_DARK)

        self.img_cache = ImageCache(self)

        # Navigation stack: list of (view_factory, args)
        self._nav_stack: list[tuple] = []
        self._current_view: Optional[ctk.CTkFrame] = None
        self._home_view: Optional[HomeView] = None

        self._build_layout()
        self.go_home()

    # ── layout ──────────────────────────────────────────────

    def _build_layout(self):
        self._sidebar = ctk.CTkFrame(self, fg_color=BG_SIDEBAR, width=SIDEBAR_W,
                                      corner_radius=0)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        # Logo / brand
        logo = ctk.CTkLabel(self._sidebar, text="📖  Manga\nReader",
                             font=ctk.CTkFont(size=16, weight="bold"),
                             text_color=ACCENT, justify="center")
        logo.pack(pady=(20, 24))

        sep = ctk.CTkFrame(self._sidebar, fg_color="#222", height=1)
        sep.pack(fill="x", padx=12, pady=(0, 12))

        self._nav_home_btn = SidebarButton(self._sidebar, text="🏠   Home",
                                            command=self.go_home)
        self._nav_home_btn.pack(fill="x", padx=8, pady=2)

        self._nav_read_btn = SidebarButton(self._sidebar, text="📖   Read",
                                            command=self.go_library)
        self._nav_read_btn.pack(fill="x", padx=8, pady=2)

        self._nav_dl_btn = SidebarButton(self._sidebar, text="📁   Downloads",
                                          command=self.go_downloads)
        self._nav_dl_btn.pack(fill="x", padx=8, pady=2)

        sep2 = ctk.CTkFrame(self._sidebar, fg_color="#222", height=1)
        sep2.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(self._sidebar, text="hentai20.io",
                     font=ctk.CTkFont(size=9), text_color="#444").pack(side="bottom", pady=8)

        self._main = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self._main.pack(side="left", fill="both", expand=True)

    def _switch_view(self, view: ctk.CTkFrame):
        if self._current_view is not None:
            self._current_view.pack_forget()
        self._current_view = view
        view.pack(in_=self._main, fill="both", expand=True)

    # ── navigation ───────────────────────────────────────────

    def go_home(self):
        self._nav_stack.clear()
        if self._home_view is None:
            self._home_view = HomeView(self._main, self)
        view = self._home_view
        self._nav_stack.append(("home", view))
        self._switch_view(view)

    def go_downloads(self):
        self._nav_stack.clear()
        view = DownloadsView(self._main, self)
        self._nav_stack.append(("downloads", view))
        self._switch_view(view)

    def go_library(self):
        self._nav_stack.clear()
        view = OfflineLibraryView(self._main, self)
        self._nav_stack.append(("library", view))
        self._switch_view(view)

    def open_manga(self, manga_url: str):
        view = MangaDetailView(self._main, self, manga_url)
        self._nav_stack.append(("manga", view))
        self._switch_view(view)

    def open_offline_manga(self, manga_path: Path):
        view = OfflineMangaDetailView(self._main, self, manga_path)
        self._nav_stack.append(("offline_manga", view))
        self._switch_view(view)

    def open_reader(self, chapter_url: str, manga_title: str, chapter_title: str):
        view = ReaderView(self._main, self, chapter_url, manga_title, chapter_title)
        self._nav_stack.append(("reader", view))
        self._switch_view(view)

    def open_offline_reader(self, chapter_path: Path, manga_title: str, chapter_title: str):
        view = OfflineReaderView(self._main, self, chapter_path, manga_title, chapter_title)
        self._nav_stack.append(("offline_reader", view))
        self._switch_view(view)

    def go_back(self):
        if len(self._nav_stack) <= 1:
            self.go_home()
            return
        self._nav_stack.pop()
        _, view = self._nav_stack[-1]
        self._switch_view(view)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
