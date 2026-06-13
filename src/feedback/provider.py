"""Analytics provider: stub (free) vs real YouTube statistics.

get_analytics_provider() returns the stub in OFFLINE_MODE, else a provider that
reads view/like/comment counts via the YouTube Data API using the stored OAuth
token (the same token used for uploading).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from config import get_settings
from db.logging import get_logger

log = get_logger("feedback.provider")

# Reading stats for your own (incl. private) videos needs the readonly scope.
YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


@dataclass
class Metrics:
    views: int = 0
    likes: int = 0
    comments: int = 0


class AnalyticsError(RuntimeError):
    pass


class AnalyticsProvider(ABC):
    name: str

    @abstractmethod
    def fetch(self, platform_video_id: str) -> Metrics:
        ...


class StubAnalyticsProvider(AnalyticsProvider):
    """Deterministic fake metrics derived from the video id — free, offline."""

    name = "stub"

    def fetch(self, platform_video_id: str) -> Metrics:
        h = int(hashlib.sha1(platform_video_id.encode()).hexdigest(), 16)
        views = h % 100_000
        likes = views // 20
        comments = views // 200
        log.info("Stub analytics", video=platform_video_id, views=views)
        return Metrics(views=views, likes=likes, comments=comments)


class YouTubeAnalyticsProvider(AnalyticsProvider):
    """Reads public statistics via the YouTube Data API (videos.list)."""

    name = "youtube"

    def __init__(self, token_file: str) -> None:
        self.token_file = token_file

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not Path(self.token_file).exists():
            raise AnalyticsError(
                f"No YouTube OAuth token at {self.token_file}. "
                "Run `python -m posting.authorize` (with the readonly scope) first."
            )
        creds = Credentials.from_authorized_user_file(self.token_file)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            Path(self.token_file).write_text(creds.to_json())
        return build("youtube", "v3", credentials=creds)

    def fetch(self, platform_video_id: str) -> Metrics:
        try:
            youtube = self._service()
            resp = (
                youtube.videos()
                .list(part="statistics", id=platform_video_id)
                .execute()
            )
            items = resp.get("items", [])
            if not items:
                return Metrics()
            stats = items[0].get("statistics", {})
            return Metrics(
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
            )
        except AnalyticsError:
            raise
        except Exception as exc:
            raise AnalyticsError(f"YouTube analytics fetch failed: {exc}") from exc


def get_analytics_provider() -> AnalyticsProvider:
    settings = get_settings()
    if settings.OFFLINE_MODE:
        return StubAnalyticsProvider()
    return YouTubeAnalyticsProvider(token_file=settings.YOUTUBE_TOKEN_FILE)
