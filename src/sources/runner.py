"""Run all available sources and persist their raw trends.

Each source is isolated: one failing source never stops the others.

    python -m sources.runner
"""

from __future__ import annotations

from db.init import init_db
from db.logging import get_logger
from sources.base import TrendSource
from sources.google_trends import GoogleTrendsSource
from sources.reddit import RedditSource
from sources.youtube import YouTubeSource

log = get_logger("sources.runner")


def build_sources() -> list[TrendSource]:
    """Instantiate every source. Reddit self-skips if unconfigured."""
    return [YouTubeSource(), GoogleTrendsSource(), RedditSource()]


def run_all() -> dict[str, int]:
    """Run all sources; return {source_name: rows_saved}."""
    init_db()
    summary: dict[str, int] = {}
    for source in build_sources():
        name = source.source.value
        try:
            ids = source.run()
            summary[name] = len(ids)
            log.info(f"{name}: saved {len(ids)} raw trends")
        except Exception as exc:
            summary[name] = 0
            log.error(f"{name} source crashed", error=str(exc))
    return summary


if __name__ == "__main__":
    result = run_all()
    print("\nFetch summary:")
    for name, count in result.items():
        print(f"  {name:>14}: {count} raw trends")
    print(f"  {'TOTAL':>14}: {sum(result.values())}")
