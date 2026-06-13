"""Pydantic schemas for structured classification output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ClassifiedTrend(BaseModel):
    """One synthesised topic Claude produces from >=1 RawTrend rows."""

    name: str = Field(description="Short, human-readable topic name, e.g. 'Bigfoot vlog'")
    summary: str = Field(description="One-to-two sentence description of the trend")
    category: str = Field(
        description="Broad category, e.g. 'creature-vlog', 'pov-skit', 'ai-music', 'meme-format'"
    )
    is_ai_trend: bool = Field(
        description="True if this is specifically an AI-generated-video trend we could produce"
    )
    momentum_score: float = Field(
        description="0-100: how fast it is rising / current viral velocity"
    )
    saturation_score: float = Field(
        description="0-100: how crowded/overdone it already is (HIGHER = MORE saturated = worse)"
    )
    fit_score: float = Field(
        description="0-100: fit for our comedic short-form AI-video format"
    )
    raw_trend_ids: list[int] = Field(
        description="IDs of the source raw_trends rows that support this topic"
    )


class ClassificationResult(BaseModel):
    """Top-level structured response: a list of deduplicated, scored topics."""

    trends: list[ClassifiedTrend]
