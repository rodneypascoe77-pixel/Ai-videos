"""Google Trends source — rising related queries for AI-video seed keywords.

Uses pytrends (unofficial). No API key, but Google rate-limits aggressively, so
calls are retried with long back-off. Metrics stored: value (rising %),
breakout flag, seed keyword.

Run standalone:
    python -m sources.google_trends
"""

from __future__ import annotations

from db.logging import get_logger
from db.models import Source
from sources._retry import api_retry
from sources.base import FetchedItem, TrendSource

log = get_logger("sources.google_trends")

_SEED_KEYWORDS = [
    "AI video",
    "AI vlog",
    "AI generated video",
    "Sora video",
    "Runway video",
]


class GoogleTrendsSource(TrendSource):
    source = Source.google_trends

    def __init__(self, geo: str = "US", timeframe: str = "now 7-d") -> None:
        self.geo = geo
        self.timeframe = timeframe

    @api_retry(max_attempts=5, min_wait=10.0, max_wait=120.0)
    def _rising(self, keyword: str) -> list[dict]:
        from pytrends.request import TrendReq  # lazy import

        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload([keyword], timeframe=self.timeframe, geo=self.geo)
        related = pytrends.related_queries()
        rising = related.get(keyword, {}).get("rising")
        if rising is None or rising.empty:
            return []
        return rising.to_dict(orient="records")

    def fetch(self) -> list[FetchedItem]:
        items: list[FetchedItem] = []
        seen: set[str] = set()

        for keyword in _SEED_KEYWORDS:
            log.debug(f"Google Trends rising for {keyword!r}")
            try:
                rows = self._rising(keyword)
            except Exception as exc:
                log.error("Google Trends fetch failed", keyword=keyword, error=str(exc))
                continue

            for row in rows:
                query = str(row.get("query", "")).strip()
                if not query or query.lower() in seen:
                    continue
                seen.add(query.lower())
                raw_value = row.get("value", 0)
                items.append(
                    FetchedItem(
                        source=self.source,
                        title=query,
                        url=(
                            "https://trends.google.com/trends/explore?q="
                            + query.replace(" ", "+")
                        ),
                        metrics={
                            "value": raw_value,
                            "breakout": raw_value == "Breakout",
                            "seed_keyword": keyword,
                        },
                    )
                )

        log.info("Google Trends fetch complete", count=len(items))
        return items


if __name__ == "__main__":
    from db.init import init_db

    init_db()
    ids = GoogleTrendsSource().run()
    print(f"Saved {len(ids)} Google Trends raw trends (ids: {ids[:10]})")
