"""Publisher abstraction: stub (free) vs real YouTube upload.

get_publisher() returns the stub in OFFLINE_MODE, otherwise a YouTubePublisher
that uploads via the YouTube Data API using a stored OAuth token.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from config import get_settings
from db.logging import get_logger
from posting.metadata import PostMetadata

log = get_logger("posting.publisher")

YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


@dataclass
class PublishResult:
    platform_video_id: str
    post_url: str


class PublisherError(RuntimeError):
    pass


class Publisher(ABC):
    name: str

    @abstractmethod
    def publish(self, video_path: str | None, meta: PostMetadata, privacy: str) -> PublishResult:
        ...


class StubPublisher(Publisher):
    """Free, offline fake upload. Returns a deterministic fake video id/URL."""

    name = "stub"

    def publish(self, video_path: str | None, meta: PostMetadata, privacy: str) -> PublishResult:
        digest = hashlib.sha1((meta.title + (video_path or "")).encode()).hexdigest()[:11]
        log.info("Stub publish", title=meta.title, privacy=privacy)
        return PublishResult(
            platform_video_id=digest,
            post_url=f"https://youtube.com/watch?v={digest}",
        )


class YouTubePublisher(Publisher):
    """Real YouTube upload via the Data API and a stored OAuth token."""

    name = "youtube"

    def __init__(self, token_file: str) -> None:
        self.token_file = token_file

    def _service(self):
        # Lazy imports so the Google libs are only needed for live posting.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        if not Path(self.token_file).exists():
            raise PublisherError(
                f"No YouTube OAuth token at {self.token_file}. "
                "Run `python -m posting.authorize` once to create it."
            )
        creds = Credentials.from_authorized_user_file(self.token_file, [YOUTUBE_UPLOAD_SCOPE])
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            Path(self.token_file).write_text(creds.to_json())
        return build("youtube", "v3", credentials=creds)

    def publish(self, video_path: str | None, meta: PostMetadata, privacy: str) -> PublishResult:
        from googleapiclient.http import MediaFileUpload

        if not video_path or not Path(video_path).exists():
            raise PublisherError(f"Video file missing for upload: {video_path}")

        youtube = self._service()
        body = {
            "snippet": {
                "title": meta.title,
                "description": meta.description,
                "tags": meta.tags,
                "categoryId": meta.category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        try:
            response = None
            while response is None:
                _status, response = request.next_chunk()
        except Exception as exc:
            raise PublisherError(f"YouTube upload failed: {exc}") from exc

        vid = response.get("id")
        if not vid:
            raise PublisherError(f"YouTube upload returned no id: {response}")
        return PublishResult(
            platform_video_id=vid,
            post_url=f"https://youtube.com/watch?v={vid}",
        )


def get_publisher() -> Publisher:
    settings = get_settings()
    if settings.OFFLINE_MODE:
        return StubPublisher()
    return YouTubePublisher(token_file=settings.YOUTUBE_TOKEN_FILE)
