"""Phase 2 orchestration: pick eligible trends, generate scripts, select best-of-N.

A trend is eligible when it is an AI-video trend still in status `new`. After its
scripts are generated and selected, the trend moves to `queued` (ready for the
video-generation phase).

    python -m generation.runner
"""

from __future__ import annotations

from config import get_settings
from db.init import init_db
from db.logging import get_logger
from db.models import Trend, TrendStatus
from db.session import session_scope
from generation.generator import DEFAULT_TARGET, ScriptGenerator
from generation.selector import DEFAULT_KEEP, ScriptSelector

log = get_logger("generation.runner")

DEFAULT_MAX_TRENDS = 3  # how many trends to process per run


def select_eligible_trend_ids(limit: int) -> list[int]:
    """Highest-scoring AI trends still in status `new`."""
    with session_scope() as session:
        rows = (
            session.query(Trend.id)
            .filter(Trend.is_ai_trend.is_(True), Trend.status == TrendStatus.new)
            .order_by(Trend.overall_score.desc().nullslast())
            .limit(limit)
            .all()
        )
        return [r[0] for r in rows]


def process_trend(
    trend_id: int,
    generator: ScriptGenerator,
    selector: ScriptSelector,
    target: int = DEFAULT_TARGET,
    keep: int = DEFAULT_KEEP,
) -> dict[str, int]:
    """Generate + select for one trend, then mark it queued."""
    generated_ids = generator.generate(trend_id, target=target)
    selected_ids = selector.select(trend_id, keep=keep)

    with session_scope() as session:
        trend = session.get(Trend, trend_id)
        if trend is not None:
            trend.status = TrendStatus.queued

    return {"generated": len(generated_ids), "selected": len(selected_ids)}


def run(max_trends: int = DEFAULT_MAX_TRENDS) -> dict[str, int]:
    init_db()
    settings = get_settings()
    trend_ids = select_eligible_trend_ids(max_trends)
    if not trend_ids:
        log.info("No eligible trends for script generation")
        return {"trends_processed": 0, "scripts_generated": 0, "scripts_selected": 0}

    generator = ScriptGenerator(model=settings.ANTHROPIC_MODEL)
    selector = ScriptSelector(model=settings.ANTHROPIC_MODEL)

    totals = {"trends_processed": 0, "scripts_generated": 0, "scripts_selected": 0}
    for trend_id in trend_ids:
        try:
            result = process_trend(trend_id, generator, selector)
        except Exception as exc:
            log.error("Script generation failed for trend", trend_id=trend_id, error=str(exc))
            continue
        totals["trends_processed"] += 1
        totals["scripts_generated"] += result["generated"]
        totals["scripts_selected"] += result["selected"]

    log.info(
        f"Script generation complete: {totals['trends_processed']} trends, "
        f"{totals['scripts_generated']} scripts, {totals['scripts_selected']} selected"
    )
    return totals


if __name__ == "__main__":
    summary = run()
    print("\nScript generation summary:")
    for k, v in summary.items():
        print(f"  {k:>18}: {v}")
