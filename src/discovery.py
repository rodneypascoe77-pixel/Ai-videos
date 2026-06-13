"""One full trend-discovery cycle: fetch raw evidence, then classify it.

Kept separate from the scheduler so it can be run/tested on its own:

    python -m discovery
"""

from __future__ import annotations

from classification.classifier import TrendClassifier
from db.init import init_db
from db.logging import get_logger
from sources.runner import run_all

log = get_logger("discovery")


def run_cycle() -> dict[str, int]:
    """Fetch from all sources, then classify the new raw trends.

    Each stage is isolated: a classification failure still leaves the fetched
    raw evidence persisted for the next cycle to pick up.
    """
    init_db()
    log.info("Discovery cycle starting")

    fetch_summary = run_all()
    raw_total = sum(fetch_summary.values())
    log.info(f"Fetch stage complete: {raw_total} raw trends across all sources")

    try:
        class_summary = TrendClassifier().run()
    except Exception as exc:
        log.error("Classification stage failed; raw evidence retained for next cycle",
                  error=str(exc))
        class_summary = {"raw_processed": 0, "trends_new": 0, "trends_updated": 0}

    result = {**{f"fetched_{k}": v for k, v in fetch_summary.items()}, **class_summary}
    log.info(
        f"Discovery cycle complete: {class_summary['trends_new']} new trends, "
        f"{class_summary['trends_updated']} updated"
    )
    return result


if __name__ == "__main__":
    summary = run_cycle()
    print("\nDiscovery cycle summary:")
    for k, v in summary.items():
        print(f"  {k:>18}: {v}")
