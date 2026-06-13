"""Collect metrics for posted videos and store performance snapshots."""

from __future__ import annotations

from db.logging import get_logger
from db.models import PerformanceSnapshot, Post, PostStatus
from db.session import session_scope
from feedback.provider import AnalyticsError, AnalyticsProvider, get_analytics_provider

log = get_logger("feedback.collector")


def collect(provider: AnalyticsProvider | None = None) -> int:
    """Fetch metrics for every successfully-posted video; store a snapshot each.

    Returns the number of snapshots written.
    """
    provider = provider or get_analytics_provider()

    with session_scope() as session:
        posts = (
            session.query(Post.id, Post.platform_video_id)
            .filter(Post.status == PostStatus.posted, Post.platform_video_id.isnot(None))
            .all()
        )
        targets = [(pid, vid) for pid, vid in posts]

    written = 0
    for post_id, platform_video_id in targets:
        try:
            metrics = provider.fetch(platform_video_id)
        except AnalyticsError as exc:
            log.error("Metrics fetch failed", post_id=post_id, error=str(exc))
            continue
        with session_scope() as session:
            session.add(
                PerformanceSnapshot(
                    post_id=post_id,
                    views=metrics.views,
                    likes=metrics.likes,
                    comments=metrics.comments,
                )
            )
        written += 1

    log.info(f"Collected {written} performance snapshots via {provider.name}")
    return written
