"""Phase 7 orchestration: collect metrics, then recompute category stats.

    python -m feedback.runner
"""

from __future__ import annotations

from db.init import init_db
from db.logging import get_logger
from feedback.aggregator import aggregate
from feedback.collector import collect

log = get_logger("feedback.runner")


def run() -> dict[str, object]:
    init_db()
    snapshots = collect()
    stats = aggregate()
    log.info(f"Feedback cycle complete: {snapshots} snapshots, {len(stats)} categories")
    return {"snapshots": snapshots, "categories": stats}


if __name__ == "__main__":
    summary = run()
    print("\nFeedback summary:")
    print(f"  snapshots: {summary['snapshots']}")
    print("  category performance:")
    for cat, s in summary["categories"].items():
        print(f"    {cat:>24}: avg {s['avg_views']} views, {s['avg_engagement']} eng "
              f"({s['n_videos']} videos)")
