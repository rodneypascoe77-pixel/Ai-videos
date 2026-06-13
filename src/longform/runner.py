"""Path B orchestration: topic -> script -> voiceover -> assembled MP4.

    python -m longform.runner
"""

from __future__ import annotations

import re

from config import DATA_DIR, get_settings
from db.logging import get_logger
from longform.assemble import build_video
from longform.script import ScriptWriter

log = get_logger("longform.runner")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "video"


def make_one(topic: str | None = None, segments: int | None = None) -> dict:
    settings = get_settings()
    n = segments or settings.LONGFORM_SEGMENTS

    script = ScriptWriter().write(settings.LONGFORM_NICHE, n, topic=topic)
    out_dir = DATA_DIR / "longform" / _slug(script.title)
    video_path = build_video(script, settings.LONGFORM_VOICE, out_dir)

    # Write the YouTube metadata alongside the file for the (later) upload step.
    (out_dir / "title.txt").write_text(script.title, encoding="utf-8")
    (out_dir / "description.txt").write_text(script.description, encoding="utf-8")

    return {
        "title": script.title,
        "description": script.description,
        "segments": len(script.segments) + 1,  # + hook
        "video_path": str(video_path),
    }


if __name__ == "__main__":
    result = make_one()
    print("\nLong-form video ready:")
    print(f"  Title:   {result['title']}")
    print(f"  Segments: {result['segments']}")
    print(f"  File:    {result['video_path']}")
