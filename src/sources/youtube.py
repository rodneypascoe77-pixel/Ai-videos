"""YouTube source — recent high-view videos around AI-video search terms.

Uses the YouTube Data API v3 (search.list + videos.list for statistics).
Metrics stored: views, likes, comments, velocity (views per hour since publish).

Run standalone:
    python -m sources.youtube
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from config import get_settings
from db.logging import get_logger
from db.models import Source
from sources._retry import api_retry
from sources.base import FetchedItem, TrendSource

log = get_logger("sources.youtube")

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

_SEED_QUERIES = [
    "AI generated video",
    "AI vlog",
    "AI animal vlog",
    "Bigfoot vlog",
    "AI character pov",
]


class YouTubeSource(TrendSource):
    source = Source.youtube

    def __init__(self, api_key: str | None = None, per_query: int = 10) -> None:
        self.api_key = api_key or get_settings().YOUTUBE_API_KEY
        self.per_query = per_query

    @api_retry()
    def _search(self, query: str, published_after: str) -> list[dict]:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                _SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "order": "viewCount",
                    "publishedAfter": published_after,
                    "maxResults": self.per_query,
                    "key": self.api_key,
                },
            )
            resp.raise_for_status()
            return resp.json().get("items", [])

    @api_retry()
    def _stats(self, video_ids: list[str]) -> dict[str, dict]:
        if not video_ids:
            return {}
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                _VIDEOS_URL,
                params={
                    "part": "statistics,snippet",
                    "id": ",".join(video_ids),
                    "key": self.api_key,
                },
            )
            resp.raise_for_status()
            return {item["id"]: item for item in resp.json().get("items", [])}

    def fetch(self) -> list[FetchedItem]:
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        items: list[FetchedItem] = []
        seen: set[str] = set()

        for query in _SEED_QUERIES:
            log.debug(f"YouTube search: {query!r}")
            try:
                results = self._search(query, published_after)
            except Exception as exc:
                log.error("YouTube search failed", query=query, error=str(exc))
                continue

            ids = [r["id"]["videoId"] for r in results if "videoId" in r.get("id", {})]
            try:
                stats = self._stats(ids)
            except Exception as exc:
                log.warning("YouTube stats failed", query=query, error=str(exc))
                stats = {}

            for vid_id in ids:
                if vid_id in seen:
                    continue
                seen.add(vid_id)
                detail = stats.get(vid_id, {})
                snippet = detail.get("snippet", {})
                statistics = detail.get("statistics", {})
                views = int(statistics.get("viewCount", 0))

                items.append(
                    FetchedItem(
                        source=self.source,
                        title=snippet.get("title", "(unknown)"),
                        description=(snippet.get("description") or "")[:1000] or None,
                        url=f"https://www.youtube.com/watch?v={vid_id}",
                        metrics={
                            "views": views,
                            "likes": int(statistics.get("likeCount", 0)),
                            "comments": int(statistics.get("commentCount", 0)),
                            "velocity": _velocity(views, snippet.get("publishedAt")),
                            "channel": snippet.get("channelTitle"),
                            "published_at": snippet.get("publishedAt"),
                            "query": query,
                        },
                    )
                )

        log.info("YouTube fetch complete", count=len(items))
        return items


def _velocity(views: int, published_at: str | None) -> float:
    """Views per hour since publish (rough momentum signal)."""
    if not published_at:
        return 0.0
    try:
        published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    hours = max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 1.0)
    return round(views / hours, 2)


if __name__ == "__main__":
    from db.init import init_db

    init_db()
    ids = YouTubeSource().run()
    print(f"Saved {len(ids)} YouTube raw trends (ids: {ids[:10]}{'...' if len(ids) > 10 else ''})")
