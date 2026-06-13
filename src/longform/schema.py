"""Pydantic schema for a faceless long-form narration script."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Segment(BaseModel):
    narration: str = Field(
        description="What the narrator says for this segment (1-3 sentences, spoken aloud)."
    )
    on_screen_text: str = Field(
        description="A short caption/keyword shown on screen for this segment (< 60 chars)."
    )


class LongformScript(BaseModel):
    title: str = Field(description="YouTube title, punchy, < 90 chars")
    description: str = Field(description="YouTube description, 1-3 sentences")
    hook: str = Field(description="A spoken opening hook for the first 5 seconds")
    segments: list[Segment] = Field(description="Ordered narration segments")
