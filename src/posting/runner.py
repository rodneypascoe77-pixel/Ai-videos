"""Phase 5 orchestration: publish QA-passed videos to YouTube.

Posts at most `max_posts` videos per run (default 1 — the pipeline is scheduled
every POST_INTERVAL_HOURS, giving the "one video every 8 hours" cadence). A video
that has already been posted is skipped via its Post rows.

    python -m posting.runner
"""

from __future__ import annotations

from datetime import datetime, timezone

from config import get_settings
from db.init import init_db
from db.logging import get_logger
from db.models import Post, PostStatus, Script, Trend, Video, VideoStatus
from db.session import session_scope
from posting.metadata import build_metadata
from posting.publisher import PublisherError, get_publisher

log = get_logger("posting.runner")

DEFAULT_MAX_POSTS = 1


def postable_video_ids(limit: int) -> list[int]:
    """QA-passed videos that have no successful Post yet, oldest first."""
    with session_scope() as session:
        posted_ids = {
            r[0]
            for r in session.query(Post.video_id)
            .filter(Post.status == PostStatus.posted)
            .all()
        }
        rows = (
            session.query(Video.id)
            .filter(Video.status == VideoStatus.qa_passed)
            .order_by(Video.id)
            .all()
        )
        ids = [r[0] for r in rows if r[0] not in posted_ids]
        return ids[:limit]


def _post_one(video_id: int, publisher, privacy: str) -> bool:
    with session_scope() as session:
        video = session.get(Video, video_id)
        script = session.get(Script, video.script_id)
        trend = session.get(Trend, script.trend_id)
        meta = build_metadata(script, trend)
        local_path = video.local_path

        post = Post(
            video_id=video_id,
            platform="youtube",
            title=meta.title,
            description=meta.description,
            tags=meta.tags,
            privacy=privacy,
            status=PostStatus.pending,
        )
        session.add(post)
        session.flush()
        post_id = post.id

    try:
        result = publisher.publish(local_path, meta, privacy)
    except PublisherError as exc:
        log.error("Publish failed", video_id=video_id, error=str(exc))
        with session_scope() as session:
            p = session.get(Post, post_id)
            p.status = PostStatus.failed
            p.error = str(exc)[:2000]
        return False

    now = datetime.now(timezone.utc)
    with session_scope() as session:
        p = session.get(Post, post_id)
        p.status = PostStatus.posted
        p.platform_video_id = result.platform_video_id
        p.post_url = result.post_url
        p.posted_at = now
        video = session.get(Video, video_id)
        video.status = VideoStatus.posted

    log.info(f"Posted video {video_id} -> {result.post_url}")
    return True


def run(max_posts: int = DEFAULT_MAX_POSTS) -> dict[str, int]:
    init_db()
    settings = get_settings()
    video_ids = postable_video_ids(max_posts)
    if not video_ids:
        log.info("No QA-passed videos to post")
        return {"posted": 0, "failed": 0}

    publisher = get_publisher()
    log.info(f"Publisher: {publisher.name}; privacy={settings.YOUTUBE_PRIVACY}")

    totals = {"posted": 0, "failed": 0}
    for vid in video_ids:
        ok = _post_one(vid, publisher, settings.YOUTUBE_PRIVACY)
        totals["posted" if ok else "failed"] += 1

    log.info(f"Posting complete: {totals['posted']} posted, {totals['failed']} failed")
    return totals


if __name__ == "__main__":
    summary = run()
    print("\nPosting summary:")
    for k, v in summary.items():
        print(f"  {k:>8}: {v}")
