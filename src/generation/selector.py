"""Select the best-of-N comedic scripts for a trend via Claude.

Scores all `generated` scripts for a trend and marks the top `keep` as `selected`
(the rest as `rejected`). Records quality_score, reasoning, and rank.

Run standalone:
    python -m generation.selector
"""

from __future__ import annotations

import anthropic

from config import get_settings
from db.logging import get_logger
from db.models import Script, ScriptStatus, Trend
from db.session import session_scope
from generation.schema import SelectionResult

log = get_logger("generation.selector")

DEFAULT_KEEP = 3

_SYSTEM_PROMPT = """\
You are a viral-content producer choosing which short-form comedic AI-video
scripts to actually produce. You receive a numbered list of candidate scripts
for a single trend.

Score each candidate 0-100 on its potential to be a funny, shareable short video,
weighing: strength of the hook, comedic payoff, originality vs the other
candidates, and how feasible it is for an AI video generator to produce.

Return ALL candidates ranked best-first. Be discerning — only truly strong
scripts should score above 75."""


class ScriptSelector:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.ANTHROPIC_MODEL

    def _score(self, candidates: list[Script]) -> SelectionResult:
        listing = "\n\n".join(
            f"[{i}] {s.title}\nPremise: {s.premise or '(none)'}\nScript: {s.script_text}"
            for i, s in enumerate(candidates)
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Rank these {len(candidates)} candidate scripts:\n\n{listing}",
                }
            ],
            output_format=SelectionResult,
        )
        return response.parsed_output

    def select(self, trend_id: int, keep: int = DEFAULT_KEEP) -> list[int]:
        """Score candidates for a trend; mark top `keep` selected. Returns selected ids."""
        with session_scope() as session:
            candidates = (
                session.query(Script)
                .filter(Script.trend_id == trend_id, Script.status == ScriptStatus.generated)
                .order_by(Script.id)
                .all()
            )
            if not candidates:
                log.info("No candidate scripts to select", trend_id=trend_id)
                return []
            session.expunge_all()

        result = self._score(candidates)

        # Map model indices back to Script ids, guard against out-of-range indices.
        ranked: list[tuple[int, float, str]] = []  # (script_id, score, reasoning)
        for rank_pos, sel in enumerate(
            sorted(result.selected, key=lambda x: -x.quality_score)
        ):
            if 0 <= sel.index < len(candidates):
                ranked.append((candidates[sel.index].id, sel.quality_score, sel.reasoning))

        selected_ids = [sid for sid, _, _ in ranked[:keep]]
        score_map = {sid: (score, reason) for sid, score, reason in ranked}

        with session_scope() as session:
            rows = (
                session.query(Script)
                .filter(Script.trend_id == trend_id, Script.status == ScriptStatus.generated)
                .all()
            )
            for row in rows:
                score_reason = score_map.get(row.id)
                if score_reason:
                    row.quality_score, row.selection_reasoning = score_reason
                if row.id in selected_ids:
                    row.status = ScriptStatus.selected
                    row.selection_rank = selected_ids.index(row.id) + 1
                else:
                    row.status = ScriptStatus.rejected

        log.info(f"Selected {len(selected_ids)} scripts for trend {trend_id}")
        return selected_ids


if __name__ == "__main__":
    from db.init import init_db

    init_db()
    with session_scope() as session:
        trend = (
            session.query(Trend)
            .join(Script, Script.trend_id == Trend.id)
            .filter(Script.status == ScriptStatus.generated)
            .first()
        )
        tid = trend.id if trend else None

    if tid is None:
        print("No trends with generated scripts. Run the generator first.")
    else:
        ids = ScriptSelector().select(tid)
        print(f"Selected {len(ids)} scripts for trend id={tid}: {ids}")
