"""Read-only queries that back the dashboard. No writes happen here."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from db.models import (
    CategoryStat,
    LogLevel,
    PipelineLog,
    Post,
    PostStatus,
    RawTrend,
    Script,
    ScriptStatus,
    Trend,
    TrendStatus,
    Video,
    VideoStatus,
)
from db.session import session_scope


def overview_stats() -> dict[str, Any]:
    """Headline counts across every stage of the pipeline."""
    with session_scope() as session:
        def count(model, *filters):
            q = session.query(func.count(model.id))
            for f in filters:
                q = q.filter(f)
            return q.scalar() or 0

        return {
            "raw_trends": count(RawTrend),
            "trends": count(Trend),
            "ai_trends": count(Trend, Trend.is_ai_trend.is_(True)),
            "scripts": count(Script),
            "scripts_selected": count(Script, Script.status == ScriptStatus.selected),
            "videos": count(Video),
            "videos_qa_passed": count(Video, Video.status == VideoStatus.qa_passed),
            "videos_posted": count(Video, Video.status == VideoStatus.posted),
            "posts": count(Post, Post.status == PostStatus.posted),
            "errors": count(PipelineLog, PipelineLog.level == LogLevel.error),
        }


def list_trends(limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = (
            session.query(Trend)
            .order_by(Trend.overall_score.desc().nullslast(), Trend.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "is_ai_trend": t.is_ai_trend,
                "overall_score": t.overall_score,
                "momentum_score": t.momentum_score,
                "saturation_score": t.saturation_score,
                "fit_score": t.fit_score,
                "status": t.status.value,
                "n_scripts": len(t.scripts),
            }
            for t in rows
        ]


def trend_detail(trend_id: int) -> dict[str, Any] | None:
    with session_scope() as session:
        t = session.get(Trend, trend_id)
        if t is None:
            return None
        scripts = sorted(t.scripts, key=lambda s: (s.selection_rank or 999, s.id))
        return {
            "id": t.id,
            "name": t.name,
            "summary": t.summary,
            "category": t.category,
            "status": t.status.value,
            "overall_score": t.overall_score,
            "scripts": [
                {
                    "id": s.id,
                    "title": s.title,
                    "premise": s.premise,
                    "status": s.status.value,
                    "quality_score": s.quality_score,
                    "selection_rank": s.selection_rank,
                    "n_videos": len(s.videos),
                }
                for s in scripts
            ],
        }


def list_videos(limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.query(Video).order_by(Video.id.desc()).limit(limit).all()
        return [
            {
                "id": v.id,
                "script_id": v.script_id,
                "provider": v.provider,
                "status": v.status.value,
                "duration_seconds": v.duration_seconds,
                "qa_notes": v.qa_notes,
                "video_url": v.video_url,
                "local_path": v.local_path,
            }
            for v in rows
        ]


def list_posts(limit: int = 100) -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = session.query(Post).order_by(Post.id.desc()).limit(limit).all()
        return [
            {
                "id": p.id,
                "video_id": p.video_id,
                "platform": p.platform,
                "title": p.title,
                "privacy": p.privacy,
                "status": p.status.value,
                "post_url": p.post_url,
                "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                "error": p.error,
            }
            for p in rows
        ]


def list_category_stats() -> list[dict[str, Any]]:
    with session_scope() as session:
        rows = (
            session.query(CategoryStat)
            .order_by(CategoryStat.avg_views.desc())
            .all()
        )
        return [
            {
                "category": c.category,
                "n_videos": c.n_videos,
                "avg_views": c.avg_views,
                "avg_engagement": c.avg_engagement,
                "total_views": c.total_views,
            }
            for c in rows
        ]


def list_logs(limit: int = 200, level: str | None = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        q = session.query(PipelineLog).order_by(PipelineLog.id.desc())
        if level:
            q = q.filter(PipelineLog.level == LogLevel(level))
        rows = q.limit(limit).all()
        return [
            {
                "id": lg.id,
                "timestamp": lg.timestamp.isoformat() if lg.timestamp else None,
                "module": lg.module,
                "level": lg.level.value,
                "message": lg.message,
            }
            for lg in rows
        ]


# Re-exported so the app module can reference status enums without re-importing.
__all__ = [
    "overview_stats",
    "list_trends",
    "trend_detail",
    "list_videos",
    "list_posts",
    "list_logs",
    "TrendStatus",
    "VideoStatus",
    "PostStatus",
]
