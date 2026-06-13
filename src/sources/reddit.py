"""Reddit source — hot posts mentioning AI video across relevant subreddits.

Uses Reddit's OAuth (client-credentials) API. Credentials are OPTIONAL: if
REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are absent, the source logs a warning
and yields nothing (the pipeline continues with its other sources).

Metrics stored: upvotes, upvote_ratio, comments, subreddit.

Run standalone:
    python -m sources.reddit
"""

from __future__ import annotations

import os

import httpx

from db.logging import get_logger
from db.models import Source
from sources._retry import api_retry
from sources.base import FetchedItem, TrendSource

log = get_logger("sources.reddit")

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_SUBREDDITS = ["artificial", "aivideo", "StableDiffusion", "ChatGPT", "singularity"]
_KEYWORDS = ("video", "vlog", "sora", "runway", "pika", "kling", "ai generat", "animat")


class RedditCredentialsMissing(RuntimeError):
    pass


class RedditSource(TrendSource):
    source = Source.reddit

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
        limit: int = 25,
    ) -> None:
        self.client_id = client_id or os.environ.get("REDDIT_CLIENT_ID", "").strip()
        self.client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
        self.user_agent = user_agent or os.environ.get(
            "REDDIT_USER_AGENT", "ai-video-creator/1.0"
        )
        self.limit = limit
        self._token: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @api_retry()
    def _get_token(self) -> str:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                _TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"User-Agent": self.user_agent},
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    @api_retry()
    def _hot(self, subreddit: str) -> list[dict]:
        if not self._token:
            self._token = self._get_token()
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"https://oauth.reddit.com/r/{subreddit}/hot",
                params={"limit": self.limit},
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "User-Agent": self.user_agent,
                },
            )
            if resp.status_code == 401:
                self._token = None  # force refresh on retry
                resp.raise_for_status()
            resp.raise_for_status()
            return resp.json()["data"]["children"]

    def fetch(self) -> list[FetchedItem]:
        if not self.configured:
            log.warning("Reddit credentials missing — skipping source")
            return []

        items: list[FetchedItem] = []
        seen: set[str] = set()

        for subreddit in _SUBREDDITS:
            log.debug(f"Reddit hot: r/{subreddit}")
            try:
                posts = self._hot(subreddit)
            except Exception as exc:
                log.error("Reddit fetch failed", subreddit=subreddit, error=str(exc))
                continue

            for post in posts:
                data = post.get("data", {})
                post_id = data.get("id", "")
                title = data.get("title", "")
                if post_id in seen or not title:
                    continue
                if not any(k in title.lower() for k in _KEYWORDS):
                    continue
                seen.add(post_id)

                items.append(
                    FetchedItem(
                        source=self.source,
                        title=title,
                        description=(data.get("selftext") or "")[:1000] or None,
                        url=f"https://reddit.com{data.get('permalink', '')}",
                        metrics={
                            "upvotes": int(data.get("score", 0)),
                            "upvote_ratio": data.get("upvote_ratio"),
                            "comments": int(data.get("num_comments", 0)),
                            "subreddit": subreddit,
                        },
                    )
                )

        log.info("Reddit fetch complete", count=len(items))
        return items


if __name__ == "__main__":
    from db.init import init_db

    init_db()
    ids = RedditSource().run()
    print(f"Saved {len(ids)} Reddit raw trends (ids: {ids[:10]})")
