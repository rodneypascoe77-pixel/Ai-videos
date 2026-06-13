"""Fetch royalty-free stock video clips from Pexels (free API).

Pexels' license allows free use (incl. monetized YouTube) with no attribution
required. If no PEXELS_API_KEY is set, callers fall back to caption slides.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from config import get_settings
from db.logging import get_logger

log = get_logger("longform.stock")

_SEARCH_URL = "https://api.pexels.com/videos/search"


def available() -> bool:
    return bool(get_settings().PEXELS_API_KEY)


def _pick_file(video: dict, max_w: int = 1920) -> str | None:
    """Choose the best HD-ish mp4 link from a Pexels video result."""
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
    if not files:
        return None
    # Prefer the largest width <= max_w; else the smallest available.
    under = [f for f in files if (f.get("width") or 0) <= max_w]
    chosen = max(under or files, key=lambda f: f.get("width") or 0)
    return chosen.get("link")


def fetch_clip(query: str, dest: Path, min_duration: float = 0.0) -> Path | None:
    """Download one landscape stock clip for `query` to `dest`. None on failure."""
    key = get_settings().PEXELS_API_KEY
    if not key:
        return None
    try:
        with httpx.Client(timeout=30, headers={"Authorization": key}) as client:
            resp = client.get(
                _SEARCH_URL,
                params={
                    "query": query,
                    "orientation": "landscape",
                    "per_page": 5,
                    "size": "medium",
                },
            )
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            if not videos:
                log.debug(f"No stock results for {query!r}")
                return None
            # Prefer a clip at least as long as the narration; else the first.
            videos.sort(key=lambda v: abs((v.get("duration") or 0) - min_duration))
            link = None
            for v in videos:
                link = _pick_file(v)
                if link:
                    break
            if not link:
                return None

            dest.parent.mkdir(parents=True, exist_ok=True)
            with client.stream("GET", link) as r:
                r.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
        return dest
    except Exception as exc:
        log.warning(f"Stock fetch failed for {query!r}", error=str(exc))
        return None
