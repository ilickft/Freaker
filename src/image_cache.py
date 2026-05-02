"""
image_cache.py – Thread-safe, LRU-bounded PIL image cache.
Keeps decoded PhotoImage objects off the main thread until needed.
"""

import io
import threading
from collections import OrderedDict
from typing import Callable

from PIL import Image, ImageTk

from scraper import fetch_image_bytes

_PLACEHOLDER_SIZE = (193, 278)


def _make_placeholder(w: int = 193, h: int = 278) -> Image.Image:
    img = Image.new("RGB", (w, h), color=(30, 30, 30))
    return img


class ImageCache:
    """
    Fetches images in background threads; calls `callback(url, PhotoImage)`
    on the main thread via `master.after(0, ...)`.
    """

    def __init__(self, master, max_size: int = 120):
        self._master = master
        self._max_size = max_size
        self._cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._pending: set[str] = set()
        self._lock = threading.Lock()

    # ── public ────────────────────────────────────────────────

    def get_thumb(
        self,
        url: str,
        size: tuple[int, int],
        callback: Callable[[str, ImageTk.PhotoImage], None],
    ) -> None:
        """Async fetch → resize → callback on main thread."""
        if not url:
            self._master.after(0, callback, url, ImageTk.PhotoImage(_make_placeholder(*size)))
            return

        with self._lock:
            if url in self._cache:
                img = self._cache[url]
                self._cache.move_to_end(url)
            elif url in self._pending:
                return
            else:
                self._pending.add(url)
                img = None

        if img is not None:
            resized = self._fit(img, size)
            tk_img = ImageTk.PhotoImage(resized)
            self._master.after(0, callback, url, tk_img)
            return

        threading.Thread(
            target=self._fetch_and_callback,
            args=(url, size, callback),
            daemon=True,
        ).start()

    def get_reader_image(
        self,
        url: str,
        max_width: int,
        callback: Callable[[str, ImageTk.PhotoImage], None],
    ) -> None:
        """Fetch full-size reader image, scale to max_width, callback."""
        if not url:
            return

        with self._lock:
            if url in self._cache:
                img = self._cache[url]
                self._cache.move_to_end(url)
            elif url in self._pending:
                return
            else:
                self._pending.add(url)
                img = None

        if img is not None:
            scaled = self._scale_to_width(img, max_width)
            tk_img = ImageTk.PhotoImage(scaled)
            self._master.after(0, callback, url, tk_img)
            return

        threading.Thread(
            target=self._fetch_reader_callback,
            args=(url, max_width, callback),
            daemon=True,
        ).start()

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    # ── private ───────────────────────────────────────────────

    def _fetch_and_callback(self, url, size, callback):
        try:
            data = fetch_image_bytes(url)
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            img = _make_placeholder(*size)

        self._store(url, img)
        resized = self._fit(img, size)
        tk_img = ImageTk.PhotoImage(resized)
        self._master.after(0, callback, url, tk_img)

    def _fetch_reader_callback(self, url, max_width, callback):
        try:
            data = fetch_image_bytes(url)
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            img = _make_placeholder(max_width, int(max_width * 1.4))

        self._store(url, img)
        scaled = self._scale_to_width(img, max_width)
        tk_img = ImageTk.PhotoImage(scaled)
        self._master.after(0, callback, url, tk_img)

    def _store(self, url, img):
        with self._lock:
            self._pending.discard(url)
            self._cache[url] = img
            self._cache.move_to_end(url)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    @staticmethod
    def _fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
        img = img.copy()
        img.thumbnail(size, Image.LANCZOS)
        canvas = Image.new("RGB", size, (20, 20, 20))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        canvas.paste(img, (x, y))
        return canvas

    @staticmethod
    def _scale_to_width(img: Image.Image, max_width: int) -> Image.Image:
        if img.width <= max_width:
            return img
        ratio = max_width / img.width
        new_h = int(img.height * ratio)
        return img.resize((max_width, new_h), Image.LANCZOS)
