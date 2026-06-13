"""Pydantic schemas for script generation and selection."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeneratedScript(BaseModel):
    """One comedic short-video script candidate."""

    title: str = Field(description="Punchy title for the video, < 80 chars")
    premise: str = Field(description="One-sentence comedic hook / setup")
    script_text: str = Field(
        description=(
            "The full short-form script: scene directions and voiceover/dialogue, "
            "tightly written for a ~30-60 second AI-generated video."
        )
    )


class ScriptBatch(BaseModel):
    """A batch of generated scripts from one generation call."""

    scripts: list[GeneratedScript]


class ScriptSelection(BaseModel):
    """The selector's verdict on one candidate script (referenced by index)."""

    index: int = Field(description="0-based index of the script in the candidate list")
    quality_score: float = Field(description="0-100 overall comedic/viral quality")
    reasoning: str = Field(description="Brief justification, < 240 chars")


class SelectionResult(BaseModel):
    """Ranked selection of the best candidates."""

    selected: list[ScriptSelection] = Field(
        description="The best candidates, best first (highest quality_score first)"
    )
