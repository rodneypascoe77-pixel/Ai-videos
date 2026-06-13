"""Classify raw evidence into scored Trend records using Claude.

Reads unclassified RawTrend rows, asks Claude (claude-sonnet-4-6 per the project
stack decision) to deduplicate them into topics and score each, then upserts
Trend rows. Uses the SDK's structured-outputs `messages.parse()` so the response
is schema-validated — no prefills, no manual JSON parsing.

overall_score is computed in Python (not by the model) so the weighting is
explicit and auditable:

    overall = 0.45*momentum + 0.40*fit + 0.15*(100 - saturation)

Note the saturation term is INVERTED: saturation_score is "higher = more
overdone = worse", so we subtract it from 100 before weighting.

Run standalone:
    python -m classification.classifier
"""

from __future__ import annotations

from datetime import datetime, timezone

import anthropic

from classification.schema import ClassificationResult, ClassifiedTrend
from config import get_settings
from db.logging import get_logger
from db.models import RawTrend, Trend, TrendStatus
from db.session import session_scope

log = get_logger("classification.classifier")

# Score weights (sum to 1.0). saturation is inverted before weighting.
_W_MOMENTUM = 0.45
_W_FIT = 0.40
_W_FRESHNESS = 0.15  # applied to (100 - saturation)

_MAX_RAW_PER_CALL = 60  # cap evidence per API call to keep prompts bounded

_SYSTEM_PROMPT = """\
You are a viral-content analyst for an automated pipeline that produces short,
comedic AI-generated videos (think: a Bigfoot filming his daily vlog).

You receive a batch of raw trend evidence scraped from YouTube, Reddit, and
Google Trends. Each item has an id, source, title, and source-native metrics.

Your job:
1. Deduplicate: cluster items that refer to the same underlying topic — even
   across different sources — into a single trend.
2. Classify each trend (is it genuinely an AI-video trend we could produce?).
3. Score each trend 0-100 on three axes:
   - momentum: how fast it is rising right now
   - saturation: how crowded/overdone it already is (HIGHER = worse)
   - fit: how well it suits our comedic short-form AI-video format
4. Link each trend back to the raw_trend_ids that support it.

Be discerning. Only mark is_ai_trend=true for genuine AI-video concepts.
A topic with no AI-video angle should still be returned but with is_ai_trend=false
and a low fit score."""


def compute_overall(momentum: float, fit: float, saturation: float) -> float:
    """Weighted blend; saturation is inverted (high saturation lowers the score)."""
    freshness = 100.0 - saturation
    overall = _W_MOMENTUM * momentum + _W_FIT * fit + _W_FRESHNESS * freshness
    return round(max(0.0, min(100.0, overall)), 2)


class TrendClassifier:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        self.model = model or settings.ANTHROPIC_MODEL

    def _load_unclassified(self, limit: int) -> list[RawTrend]:
        """RawTrend rows not yet linked to any Trend.raw_trend_ids."""
        with session_scope() as session:
            used: set[int] = set()
            for (ids,) in session.query(Trend.raw_trend_ids).all():
                if ids:
                    used.update(ids)

            query = session.query(RawTrend).order_by(RawTrend.fetched_at.desc())
            rows = [r for r in query.all() if r.id not in used][:limit]
            # Detach: copy the fields we need so they survive session close
            session.expunge_all()
            return rows

    def _build_evidence(self, rows: list[RawTrend]) -> str:
        lines = []
        for r in rows:
            metrics = r.metrics_json or {}
            metric_str = ", ".join(f"{k}={v}" for k, v in metrics.items() if v is not None)
            lines.append(
                f"[id={r.id}] ({r.source.value}) {r.title!r}"
                + (f" | {metric_str}" if metric_str else "")
            )
        return "\n".join(lines)

    def _call_model(self, evidence: str, count: int) -> ClassificationResult:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Here are {count} raw trend items. Deduplicate, classify, and "
                        f"score them:\n\n{evidence}"
                    ),
                }
            ],
            output_format=ClassificationResult,
        )
        return response.parsed_output

    def _upsert(self, classified: list[ClassifiedTrend]) -> tuple[int, int]:
        """Insert new Trends or merge into existing ones by name. Returns (new, updated)."""
        now = datetime.now(timezone.utc)
        new_count = updated = 0
        with session_scope() as session:
            for ct in classified:
                overall = compute_overall(ct.momentum_score, ct.fit_score, ct.saturation_score)
                existing = (
                    session.query(Trend).filter(Trend.name == ct.name).one_or_none()
                )
                if existing is None:
                    session.add(
                        Trend(
                            name=ct.name,
                            summary=ct.summary,
                            category=ct.category,
                            is_ai_trend=ct.is_ai_trend,
                            momentum_score=ct.momentum_score,
                            saturation_score=ct.saturation_score,
                            fit_score=ct.fit_score,
                            overall_score=overall,
                            status=TrendStatus.new,
                            raw_trend_ids=sorted(set(ct.raw_trend_ids)),
                        )
                    )
                    new_count += 1
                else:
                    # Merge evidence + refresh scores
                    merged = sorted(set((existing.raw_trend_ids or []) + ct.raw_trend_ids))
                    existing.raw_trend_ids = merged
                    existing.summary = ct.summary
                    existing.category = ct.category
                    existing.is_ai_trend = ct.is_ai_trend
                    existing.momentum_score = ct.momentum_score
                    existing.saturation_score = ct.saturation_score
                    existing.fit_score = ct.fit_score
                    existing.overall_score = overall
                    existing.last_updated = now
                    updated += 1
        return new_count, updated

    def run(self) -> dict[str, int]:
        """Classify all currently-unclassified raw trends. Returns summary counts."""
        rows = self._load_unclassified(_MAX_RAW_PER_CALL)
        if not rows:
            log.info("No unclassified raw trends to process")
            return {"raw_processed": 0, "trends_new": 0, "trends_updated": 0}

        log.info(f"Classifying {len(rows)} raw trends")
        evidence = self._build_evidence(rows)
        try:
            result = self._call_model(evidence, len(rows))
        except Exception as exc:
            log.error("Classification API call failed", error=str(exc))
            raise

        new_count, updated = self._upsert(result.trends)
        log.info(
            f"Classification complete: {len(result.trends)} topics "
            f"({new_count} new, {updated} updated)"
        )
        return {
            "raw_processed": len(rows),
            "trends_new": new_count,
            "trends_updated": updated,
        }


if __name__ == "__main__":
    from db.init import init_db

    init_db()
    summary = TrendClassifier().run()
    print("\nClassification summary:")
    for k, v in summary.items():
        print(f"  {k:>16}: {v}")

    # Show the current top trends
    with session_scope() as session:
        top = (
            session.query(Trend)
            .filter(Trend.is_ai_trend.is_(True))
            .order_by(Trend.overall_score.desc())
            .limit(10)
            .all()
        )
        if top:
            print("\nTop AI-video trends:")
            for t in top:
                print(f"  {t.overall_score:5.1f}  {t.name}  [{t.status.value}]")
