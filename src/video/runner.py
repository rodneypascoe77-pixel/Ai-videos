"""Phase 3 orchestration: produce videos for queued trends' selected scripts.

A trend in status `queued` has its best-of-N scripts (status `selected`). For each
selected script we generate a video; once a trend's scripts are all processed the
trend moves to `used`.

    python -m video.runner
"""

from __future__ import annotations

from db.init import init_db
from db.logging import get_logger
from db.models import Script, ScriptStatus, Trend, TrendStatus
from db.session import session_scope
from video.generator import VideoGenerator
from video.provider import get_provider

log = get_logger("video.runner")

DEFAULT_MAX_TRENDS = 1  # videos cost money in live mode — process conservatively


def select_queued_trend_ids(limit: int) -> list[int]:
    """Queued AI trends, highest score first."""
    with session_scope() as session:
        rows = (
            session.query(Trend.id)
            .filter(Trend.status == TrendStatus.queued)
            .order_by(Trend.overall_score.desc().nullslast())
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]


def selected_script_ids(trend_id: int) -> list[int]:
    with session_scope() as session:
        rows = (
            session.query(Script.id)
            .filter(Script.trend_id == trend_id, Script.status == ScriptStatus.selected)
            .order_by(Script.selection_rank)
            .all()
        )
        return [r[0] for r in rows]


def run(max_trends: int = DEFAULT_MAX_TRENDS) -> dict[str, int]:
    init_db()
    trend_ids = select_queued_trend_ids(max_trends)
    if not trend_ids:
        log.info("No queued trends for video generation")
        return {"trends_processed": 0, "videos_completed": 0, "videos_failed": 0}

    generator = VideoGenerator(provider=get_provider())
    log.info(f"Video provider: {generator.provider.name}")

    totals = {"trends_processed": 0, "videos_completed": 0, "videos_failed": 0}
    for trend_id in trend_ids:
        script_ids = selected_script_ids(trend_id)
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
