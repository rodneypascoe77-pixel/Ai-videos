"""Aggregate the latest snapshot of each posted video into per-category stats.

This is the pipeline's learned memory: which comedic categories actually perform.
The trend classifier reads these stats (via category_hints) to weight future scoring.
"""

from __future__ import annotations

from db.logging import get_logger
from db.models import (
    CategoryStat,
    PerformanceSnapshot,
    Post,
    Script,
    Trend,
    Video,
)
from db.session import session_scope

log = get_logger("feedback.aggregator")


def _latest_snapshot_per_post(session) -> dict[int, PerformanceSnapshot]:
    """Most recent snapshot for each post_id."""
    latest: dict[int, PerformanceSnapshot] = {}
    for snap in session.query(PerformanceSnapshot).order_by(PerformanceSnapshot.id).all():
        latest[snap.post_id] = snap  # later id overwrites -> newest wins
    return latest


def aggregate() -> dict[str, dict]:
    """Recompute category_stats from the latest snapshots. Returns the new stats."""
    with session_scope() as session:
        latest = _latest_snapshot_per_post(session)
        if not latest:
            log.info("No snapshots to aggregate")
            return {}

        # Map each post -> trend category via post.video.script.trend.
        # Accumulate views/engagement per category.
        acc: dict[str, dict[str, int]] = {}
        for post_id, snap in latest.items():
            post = session.get(Post, post_id)
            if post is None:
                continue
            video = session.get(Video, post.video_id)
            if video is None:
                continue
            script = session.get(Script, video.script_id)
            if script is None:
                continue
            trend = session.get(Trend, script.trend_id)
            category = (trend.category if trend else None) or "uncategorized"

            bucket = acc.setdefault(category, {"n": 0, "views": 0, "eng": 0})
            bucket["n"] += 1
            bucket["views"] += snap.views
            bucket["eng"] += snap.likes + snap.comments

        # Upsert CategoryStat rows.
        result: dict[str, dict] = {}
        for category, b in acc.items():
            n = b["n"] or 1
            avg_views = b["views"] / n
            avg_eng = b["eng"] / n
            stat = session.get(CategoryStat, category)
            if stat is None:
                stat = CategoryStat(category=category)
                session.add(stat)
            stat.n_videos = b["n"]
            stat.total_views = b["views"]
            stat.total_engagement = b["eng"]
            stat.avg_views = avg_views
            stat.avg_engagement = avg_eng
            result[category] = {
                "n_videos": b["n"],
                "avg_views": round(avg_views, 1),
                "avg_engagement": round(avg_eng, 1),
            }

    log.info(f"Aggregated performance for {len(result)} categories")
    return result


def category_hints(top_k: int = 5) -> str:
    """A short natural-language summary of category performance for the classifier.

    Empty string when there's no data yet (so the classifier prompt is unchanged
    on a cold start).
    """
    with session_scope() as session:
        stats = (
            session.query(CategoryStat)
            .filter(CategoryStat.n_videos > 0)
            .order_by(CategoryStat.avg_views.desc())
            .limit(top_k)
            .all()
        )
        if not stats:
            return ""
        lines = [
            f"- {s.category}: avg {int(s.avg_views)} views, "
            f"{int(s.avg_engagement)} engagement ({s.n_videos} videos)"
            for s in stats
        ]
    return (
        "Historical performance of our past videos by category "
        "(higher = better; favor strong categories when scoring fit):\n"
        + "\n".join(lines)
    )
