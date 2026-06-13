"""Generate a faceless long-form narration script with Claude."""

from __future__ import annotations

import anthropic

from config import get_settings
from db.logging import get_logger
from longform.schema import LongformScript

log = get_logger("longform.script")

_SYSTEM = """\
You write scripts for faceless, narrated YouTube videos — the kind with a calm
authoritative voiceover over simple visuals, in niches like fascinating facts,
space, history, mysteries, and science.

Write for the EAR: short, punchy spoken sentences, a strong hook in the first
5 seconds, smooth transitions, and a satisfying closer. Each segment is one
beat of narration plus a short on-screen caption (a keyword or mini-headline).
Keep it accurate and genuinely interesting — no fluff, no "in this video"."""


class ScriptWriter:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        s = get_settings()
        self.client = anthropic.Anthropic(api_key=api_key or s.ANTHROPIC_API_KEY)
        self.model = model or s.ANTHROPIC_MODEL

    def write(self, niche: str, segments: int, topic: str | None = None) -> LongformScript:
        ask_topic = (
            f"Topic: {topic}." if topic else f"Pick one compelling specific topic in: {niche}."
        )
        prompt = (
            f"{ask_topic}\n\n"
            f"Write a faceless narrated video script with exactly {segments} segments. "
            "Make the hook irresistible and each segment build curiosity."
        )
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=LongformScript,
        )
        script = resp.parsed_output
        log.info(f"Wrote long-form script: {script.title!r} ({len(script.segments)} segments)")
        return script


if __name__ == "__main__":
    s = get_settings()
    script = ScriptWriter().write(s.LONGFORM_NICHE, s.LONGFORM_SEGMENTS)
    print(f"\nTITLE: {script.title}")
    print(f"HOOK:  {script.hook}\n")
    for i, seg in enumerate(script.segments, 1):
        print(f"[{i}] ({seg.on_screen_text})  {seg.narration}")
