"""
scraper.py – All network & HTML-parsing logic for hentai20.io
No UI imports; returns plain Python dicts/lists.
"""

import re
import json
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://hentai20.io"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

IMG_HEADERS = {
    **HEADERS,
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _get(url: str, timeout: int = 15) -> BeautifulSoup:
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


# ────────────────────────────────────────────────────────────
# HOME / BROWSE
# ────────────────────────────────────────────────────────────

def fetch_home(page: int = 1) -> list[dict]:
    """
    Returns list of:
        {"title": str, "url": str, "thumb": str, "latest_chapter": str}
    """
    url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
    soup = _get(url)
    results = []
    for card in soup.select(".bsx"):
        a = card.select_one("a")
        if not a:
            continue
        img = a.select_one("img")
        latest = card.select_one(".epxs")
        results.append(
            {
                "title": a.get("title", "").strip() or card.select_one(".tt").text.strip(),
                "url": a.get("href", ""),
                "thumb": (img.get("src") or img.get("data-src") or img.get("data-lazy-src") or "")
                if img
                else "",
                "latest_chapter": latest.text.strip() if latest else "",
            }
        )
    return results


def search_manga(query: str) -> list[dict]:
    """Simple search via site's built-in search."""
    url = f"{BASE_URL}/?s={requests.utils.quote(query)}"
    soup = _get(url)
    results = []
    for card in soup.select(".bsx"):
        a = card.select_one("a")
        if not a:
            continue
        img = a.select_one("img")
        latest = card.select_one(".epxs")
        results.append(
            {
                "title": a.get("title", "").strip(),
                "url": a.get("href", ""),
                "thumb": (img.get("src") or img.get("data-src") or "")
                if img
                else "",
                "latest_chapter": latest.text.strip() if latest else "",
            }
        )
    return results


# ────────────────────────────────────────────────────────────
# MANGA DETAIL PAGE
# ────────────────────────────────────────────────────────────

def fetch_manga_detail(manga_url: str) -> dict:
    """
    Returns:
        {
            "title": str,
            "cover": str,
            "synopsis": str,
            "status": str,
            "genres": [str],
            "chapters": [{"title": str, "url": str, "date": str}]
                         newest-first order from site
        }
    """
    soup = _get(manga_url)

    title_el = soup.select_one(".entry-title, h1.entry-title")
    title = title_el.text.strip() if title_el else "Unknown"

    cover_el = soup.select_one(".thumb img")
    cover = ""
    if cover_el:
        cover = (
            cover_el.get("src")
            or cover_el.get("data-src")
            or cover_el.get("data-lazy-src")
            or ""
        )

    # Synopsis – first real paragraph inside .entry-content
    syn_el = soup.select_one(".entry-content p, .synopsis p, .wd-full p")
    synopsis = syn_el.text.strip() if syn_el else ""

    # Info rows
    status = ""
    genres: list[str] = []
    for row in soup.select(".tsinfo .imptdt"):
        label = row.select_one("h1, b, i, span")
        text = row.text.strip()
        if "status" in text.lower() or (label and "status" in label.text.lower()):
            a = row.select_one("a")
            status = a.text.strip() if a else text
        genre_links = row.select("a[href*='genre'], a[href*='genres']")
        genres += [g.text.strip() for g in genre_links]

    # Genres from dedicated block
    if not genres:
        for g in soup.select(".mgen a"):
            genres.append(g.text.strip())

    # Chapters
    chapters = []
    for item in soup.select("#chapterlist .eph-num"):
        a = item.select_one("a")
        if not a or not a.get("href", "").startswith("http"):
            continue
        ch_title_el = a.select_one(".chapternum")
        ch_date_el = a.select_one(".chapterdate")
        chapters.append(
            {
                "title": ch_title_el.text.strip() if ch_title_el else a.text.strip(),
                "url": a["href"],
                "date": ch_date_el.text.strip() if ch_date_el else "",
            }
        )

    return {
        "title": title,
        "cover": cover,
        "synopsis": synopsis,
        "status": status,
        "genres": genres,
        "chapters": chapters,  # newest first
    }


# ────────────────────────────────────────────────────────────
# CHAPTER READER PAGE
# ────────────────────────────────────────────────────────────

def fetch_chapter_images(chapter_url: str) -> dict:
    """
    Returns:
        {
            "images": [str],   # direct CDN URLs
            "prev_url": str,
            "next_url": str,
            "chapter_title": str,
        }
    """
    soup = _get(chapter_url)

    # Primary: ts_reader.run({...}) JSON embedded in <script>
    images: list[str] = []
    prev_url = ""
    next_url = ""

    for script in soup.find_all("script"):
        text = script.string or ""
        if "ts_reader.run" in text:
            m = re.search(r"ts_reader\.run\((\{.*?\})\)", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1))
                    sources = data.get("sources", [])
                    if sources:
                        images = sources[0].get("images", [])
                    prev_url = data.get("prevUrl", "")
                    next_url = data.get("nextUrl", "")
                except json.JSONDecodeError:
                    pass
            break

    # Fallback: #readerarea img tags
    if not images:
        for img in soup.select("#readerarea img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy-src")
                or ""
            )
            if src and src.endswith((".jpg", ".jpeg", ".png", ".webp")):
                images.append(src)

    chapter_title_el = soup.select_one(".headpost h1, .entry-title, .chaptertitle")
    chapter_title = chapter_title_el.text.strip() if chapter_title_el else ""

    return {
        "images": images,
        "prev_url": prev_url,
        "next_url": next_url,
        "chapter_title": chapter_title,
    }


# ────────────────────────────────────────────────────────────
# IMAGE BYTES (used by both reader and downloader)
# ────────────────────────────────────────────────────────────

def fetch_image_bytes(url: str, timeout: int = 20) -> bytes:
    r = SESSION.get(url, headers=IMG_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.content
