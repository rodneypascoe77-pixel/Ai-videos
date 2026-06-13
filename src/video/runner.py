"""Phase 3 orchestration: produce videos for queued trends' selected scripts.

Cost-controlled (Lean profile): only generates videos for trends scoring at or
above VIDEO_MIN_TREND_SCORE, only the top VIDEO_SCRIPTS_PER_TREND script(s) per
trend, and skips entirely when the unposted-video backlog is already at
VIDEO_MAX_BACKLOG — so we never pay to generate more than we'll actually post.

    python -m video.runner
"""

from __future__ import annotations

from config import get_settings
from db.init import init_db
from db.logging import get_logger
from db.models import Post, PostStatus, Script, ScriptStatus, Trend, TrendStatus, Video, VideoStatus
from db.session import session_scope
from video.generator import VideoGenerator
from video.provider import get_provider

log = get_logger("video.runner")

DEFAULT_MAX_TRENDS = 1  # videos cost money in live mode — process conservatively


def unposted_video_backlog() -> int:
    """Count videos that are made/QA'd but not yet posted (the spend we'd waste)."""
    with session_scope() as session:
        posted_ids = {
            r[0] for r in session.query(Post.video_id).filter(Post.status == PostStatus.posted)
        }
        rows = (
            session.query(Video.id)
            .filter(Video.status.in_([VideoStatus.completed, VideoStatus.qa_passed]))
            .all()
        )
        return sum(1 for r in rows if r[0] not in posted_ids)


def select_queued_trend_ids(limit: int, min_score: float) -> list[int]:
    """Queued AI trends scoring >= min_score, highest score first."""
    with session_scope() as session:
        rows = (
            session.query(Trend.id)
            .filter(
                Trend.status == TrendStatus.queued,
                Trend.overall_score >= min_score,
            )
            .order_by(Trend.overall_score.desc().nullslast())
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]


def selected_script_ids(trend_id: int, top_n: int) -> list[int]:
    """The top `top_n` selected scripts for a trend, by selection rank."""
    with session_scope() as session:
        rows = (
            session.query(Script.id)
            .filter(Script.trend_id == trend_id, Script.status == ScriptStatus.selected)
            .order_by(Script.selection_rank)
            .limit(top_n)
            .all()
        )
        return [r[0] for r in rows]


def run(max_trends: int = DEFAULT_MAX_TRENDS) -> dict[str, int]:
    init_db()
    settings = get_settings()

    # Cost gate: don't generate if we already have enough unposted videos queued up.
    backlog = unposted_video_backlog()
    if backlog >= settings.VIDEO_MAX_BACKLOG:
        log.info(
            f"Skipping video generation — backlog {backlog} "
            f">= VIDEO_MAX_BACKLOG {settings.VIDEO_MAX_BACKLOG} (cost control)"
        )
        return {"trends_processed": 0, "videos_completed": 0, "videos_failed": 0}

    trend_ids = select_queued_trend_ids(max_trends, settings.VIDEO_MIN_TREND_SCORE)
    if not trend_ids:
        log.info(
            f"No queued trends scoring >= {settings.VIDEO_MIN_TREND_SCORE} for video generation"
        )
        return {"trends_processed": 0, "videos_completed": 0, "videos_failed": 0}

    generator = VideoGenerator(provider=get_provider())
    log.info(
        f"Video provider: {generator.provider.name}; backlog={backlog}; "
        f"{settings.VIDEO_SCRIPTS_PER_TREND} script(s)/trend"
    )

    totals = {"trends_processed": 0, "videos_completed": 0, "videos_failed": 0}
    for trend_id in trend_ids:
        script_ids = selected_script_ids(trend_id, settings.VIDEO_SCRIPTS_PER_TREND)
        if not script_ids:
            log.warning("Queued trend has no selected scripts", trend_id=trend_id)
            continue

        for sid in script_ids:
            try:
                video_id = generator.generate_for_script(sid)
            except Exception as exc:
                log.error("Video generation crashed", script_id=sid, error=str(exc))
                video_id = None
            if video_id is not None:
                totals["videos_completed"] += 1
            else:
                totals["videos_failed"] += 1

        with session_scope() as session:
            trend = session.get(Trend, trend_id)
            if trend is not None:
                trend.status = TrendStatus.used
        totals["trends_processed"] += 1

    log.info(
        f"Video generation complete: {totals['trends_processed']} trends, "
        f"{totals['videos_completed']} videos ({totals['videos_failed']} failed)"
    )
    return totals


if __name__ == "__main__":
    summary = run()
    print("\nVideo generation summary:")
    for k, v in summary.items():
        print(f"  {k:>18}: {v}")
