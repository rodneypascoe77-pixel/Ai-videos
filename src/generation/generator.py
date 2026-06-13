"""Generate comedic script candidates for a trend via Claude.

Generates N scripts (default 25) in several smaller batches rather than one giant
call: smaller batches keep each response well within token limits and, by seeding
each batch with a different comedic angle, produce more variety than asking for 25
at once.

Run standalone (uses the top unprocessed AI trend):
    python -m generation.generator
"""

from __future__ import annotations

import anthropic

from config import get_settings
from db.logging import get_logger
from db.models import Script, ScriptStatus, Trend
from db.session import session_scope
from generation.schema import ScriptBatch

log = get_logger("generation.generator")

DEFAULT_TARGET = 25
_BATCH_SIZE = 5  # scripts per API call

# Distinct comedic angles to seed batches with, for variety across the 25.
_ANGLES = [
    "mundane everyday situations played absurdly straight",
    "fish-out-of-water reactions to modern technology",
    "over-dramatic narration of trivial events",
    "wholesome but unexpectedly chaotic moments",
    "deadpan documentary / nature-doc parody style",
    "escalating misunderstandings",
    "breaking-the-fourth-wall self-aware humor",
]

_SYSTEM_PROMPT = """\
You are a comedy writer for short-form AI-generated videos (15-60 seconds),
the kind that go viral on YouTube Shorts and TikTok (e.g. a Bigfoot calmly
vlogging his morning routine).

Write tight, visual, genuinely funny scripts that an AI video generator can
realistically produce: simple settings, a clear comedic premise, a strong hook
in the first 2 seconds, and a payoff. Favor visual comedy and absurd-but-relatable
situations over dialogue-heavy bits."""


class ScriptGenerator:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.ANTHROPIC_MODEL

    def _generate_batch(self, trend: Trend, angle: str, n: int) -> ScriptBatch:
        prompt = (
            f"Trend: {trend.name!r}\n"
            f"Summary: {trend.summary or '(none)'}\n"
            f"Category: {trend.category or '(none)'}\n\n"
            f"Write {n} distinct comedic short-video scripts for this trend.\n"
            f"For this batch, lean into the comedic angle: {angle}.\n"
            f"Make each script clearly different from the others."
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            output_format=ScriptBatch,
        )
        return response.parsed_output

    def generate(self, trend_id: int, target: int = DEFAULT_TARGET) -> list[int]:
        """Generate `target` scripts for a trend; persist them. Returns new Script ids."""
        with session_scope() as session:
            trend = session.get(Trend, trend_id)
            if trend is None:
                raise ValueError(f"Trend {trend_id} not found")
            # Detach a lightweight copy of the fields we need
            trend_snapshot = Trend(
                id=trend.id, name=trend.name, summary=trend.summary, category=trend.category
            )

        produced: list[ScriptBatch] = []
        made = 0
        angle_idx = 0
        while made < target:
            n = min(_BATCH_SIZE, target - made)
            angle = _ANGLES[angle_idx % len(_ANGLES)]
            angle_idx += 1
            try:
                batch = self._generate_batch(trend_snapshot, angle, n)
            except Exception as exc:
                log.error("Script batch generation failed", trend_id=trend_id, error=str(exc))
                break
            produced.append(batch)
            made += len(batch.scripts)

        new_ids: list[int] = []
        with session_scope() as session:
            for batch in produced:
                for gs in batch.scripts:
                    row = Script(
                        trend_id=trend_id,
                        title=gs.title[:512],
                        premise=gs.premise,
                        script_text=gs.script_text,
                        status=ScriptStatus.generated,
                    )
                    session.add(row)
                    session.flush()
                    new_ids.append(row.id)

        log.info(f"Generated {len(new_ids)} scripts for trend {trend_id}")
        return new_ids


if __name__ == "__main__":
    from db.init import init_db

    init_db()
    with session_scope() as session:
        top = (
            session.query(Trend)
            .filter(Trend.is_ai_trend.is_(True))
            .order_by(Trend.overall_score.desc())
            .first()
        )
        tid = top.id if top else None
        tname = top.name if top else None

    if tid is None:
        print("No AI trends available. Run discovery first.")
    else:
        ids = ScriptGenerator().generate(tid)
        print(f"Generated {len(ids)} scripts for trend {tname!r} (id={tid}).")
