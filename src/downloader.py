"""
downloader.py – Chapter download logic (runs in a background thread).
Calls back into the UI via a thread-safe queue/callback pattern.
"""

import os
import re
import threading
from pathlib import Path
from typing import Callable

from scraper import fetch_chapter_images, fetch_image_bytes

# Downloads land in <user home>/MangaReader Downloads/
DEFAULT_DOWNLOAD_ROOT = Path.home() / "MangaReader Downloads"


def _sanitise(name: str) -> str:
    """Make a safe directory/file name."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    return name.strip().strip(".")[:120] or "unknown"


def download_chapter(
    chapter_url: str,
    manga_title: str,
    chapter_title: str,
    on_progress: Callable[[int, int], None],   # (current, total)
    on_done: Callable[[str], None],            # (download_dir)
    on_error: Callable[[str], None],           # (error_message)
    stop_event: threading.Event | None = None,
    download_root: Path = DEFAULT_DOWNLOAD_ROOT,
) -> None:
    """
    Runs synchronously – call it from a daemon thread.
    Downloads all images to:
        <download_root>/<manga_title>/<chapter_title>/01.jpg …
    """
    try:
        chapter_data = fetch_chapter_images(chapter_url)
        images = chapter_data["images"]
        if not images:
            on_error("No images found in this chapter.")
            return

        dest = download_root / _sanitise(manga_title) / _sanitise(chapter_title)
        dest.mkdir(parents=True, exist_ok=True)

        total = len(images)
        on_progress(0, total)

        for idx, url in enumerate(images, start=1):
            if stop_event and stop_event.is_set():
                on_error("Download cancelled.")
                return

            ext = url.rsplit(".", 1)[-1].lower()
            if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                ext = "jpg"
            filename = dest / f"{idx:03d}.{ext}"

            # Skip if already downloaded
            if filename.exists() and filename.stat().st_size > 0:
                on_progress(idx, total)
                continue

            data = fetch_image_bytes(url)
            filename.write_bytes(data)
            on_progress(idx, total)

        on_done(str(dest))

    except Exception as exc:
        on_error(str(exc))


def start_download_thread(
    chapter_url: str,
    manga_title: str,
    chapter_title: str,
    on_progress: Callable[[int, int], None],
    on_done: Callable[[str], None],
    on_error: Callable[[str], None],
    stop_event: threading.Event | None = None,
) -> tuple[threading.Thread, threading.Event]:
    """Spawns and starts the download thread. Returns (thread, stop_event)."""
    if stop_event is None:
        stop_event = threading.Event()

    t = threading.Thread(
        target=download_chapter,
        args=(
            chapter_url,
            manga_title,
            chapter_title,
            on_progress,
            on_done,
            on_error,
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    return t, stop_event
