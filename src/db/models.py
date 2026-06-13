"""SQLAlchemy ORM models for the trend pipeline.

Two-tier design:
  * RawTrend  — immutable raw evidence pulled from a single source/item.
  * Trend     — a deduplicated, AI-classified topic synthesised from >=1 RawTrend.
  * PipelineLog — structured log rows (the dashboard reads these later).

Only these Phase 1 tables exist now; later phases add tables to the same DB.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Source(str, enum.Enum):
    youtube = "youtube"
    google_trends = "google_trends"
    reddit = "reddit"


class TrendStatus(str, enum.Enum):
    new = "new"          # freshly classified, not yet acted on
    queued = "queued"    # selected for script/video generation
    used = "used"        # a video was produced from it
    expired = "expired"  # momentum gone / saturated before use


class ScriptStatus(str, enum.Enum):
    generated = "generated"  # one of the N candidates produced for a trend
    selected = "selected"    # chosen as a best-of-N for video generation
    rejected = "rejected"    # not selected
    used = "used"            # a video was produced from it


class VideoStatus(str, enum.Enum):
    pending = "pending"        # row created, not yet submitted to the provider
    generating = "generating"  # submitted, provider job running
    completed = "completed"    # video produced, URL available
    failed = "failed"          # provider job failed


class LogLevel(str, enum.Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


# ---------------------------------------------------------------------------
# RawTrend — raw evidence, one row per source item
# ---------------------------------------------------------------------------


class RawTrend(Base):
    """A single raw item fetched from one source (a video, a search query, a post).

    This is append-only evidence. We never overwrite a RawTrend; classification
    reads many of these and synthesises Trend rows from them.
    """

    __tablename__ = "raw_trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[Source] = mapped_column(Enum(Source), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    # Source-native metrics: e.g. {"views": 1200000, "velocity": 4.2, "upvotes": 8100}
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), nullable=False, index=True
    )


# ---------------------------------------------------------------------------
# Trend — synthesised, AI-classified topic
# ---------------------------------------------------------------------------


class Trend(Base):
    """A deduplicated topic the pipeline cares about, scored by Claude.

    Synthesised from one or more RawTrend rows (linked via raw_trend_ids).
    This is the mutable, decision-bearing record: its status and scores change
    over its lifecycle.
    """

    __tablename__ = "trends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(128))
    is_ai_trend: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Scores (0-100). overall_score is a weighted combination of the others.
    momentum_score: Mapped[float | None] = mapped_column(Float)     # how fast it's rising
    saturation_score: Mapped[float | None] = mapped_column(Float)   # how overdone (high=bad)
    fit_score: Mapped[float | None] = mapped_column(Float)          # fit for our comedic format
    overall_score: Mapped[float | None] = mapped_column(Float)

    status: Mapped[TrendStatus] = mapped_column(
        Enum(TrendStatus), default=TrendStatus.new, nullable=False, index=True
    )

    # Back-links to the RawTrend evidence rows, e.g. [12, 47, 103]
    raw_trend_ids: Mapped[list | None] = mapped_column(JSON)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), nullable=False
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
        nullable=False,
    )

    scripts: Mapped[list["Script"]] = relationship(
        "Script", back_populates="trend", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Script — a comedic script candidate generated for a Trend (Phase 2)
# ---------------------------------------------------------------------------


class Script(Base):
    """One generated comedic script for a trend.

    Phase 2 generates many candidates per trend (status=generated), then selects
    the best few (status=selected) for video generation in a later phase.
    """

    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trend_id: Mapped[int] = mapped_column(
        ForeignKey("trends.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    premise: Mapped[str | None] = mapped_column(Text)       # one-line comedic hook
    script_text: Mapped[str] = mapped_column(Text, nullable=False)  # the actual VO/scene text

    status: Mapped[ScriptStatus] = mapped_column(
        Enum(ScriptStatus), default=ScriptStatus.generated, nullable=False, index=True
    )
    # Selection scoring (populated by the selector for the chosen scripts)
    quality_score: Mapped[float | None] = mapped_column(Float)   # 0-100
    selection_reasoning: Mapped[str | None] = mapped_column(Text)
    selection_rank: Mapped[int | None] = mapped_column(Integer)  # 1 = best

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), nullable=False
    )

    trend: Mapped["Trend"] = relationship("Trend", back_populates="scripts")
    videos: Mapped[list["Video"]] = relationship(
        "Video", back_populates="script", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Video — a generated video for a Script (Phase 3)
# ---------------------------------------------------------------------------


class Video(Base):
    """A video produced from a selected script via a video-generation provider."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # "runway" / "stub"
    prompt_text: Mapped[str | None] = mapped_column(Text)   # motion/scene prompt sent to provider
    image_prompt: Mapped[str | None] = mapped_column(Text)  # text-to-image prompt (first frame)

    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus), default=VideoStatus.pending, nullable=False, index=True
    )
    provider_job_id: Mapped[str | None] = mapped_column(String(128))
    video_url: Mapped[str | None] = mapped_column(String(2048))
    error: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    script: Mapped["Script"] = relationship("Script", back_populates="videos")


# ---------------------------------------------------------------------------
# PipelineLog — structured logging sink
# ---------------------------------------------------------------------------


class PipelineLog(Base):
    """Structured log entries written by every module (dashboard reads this)."""

    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), nullable=False, index=True
    )
    module: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[LogLevel] = mapped_column(Enum(LogLevel), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict | None] = mapped_column(JSON)
