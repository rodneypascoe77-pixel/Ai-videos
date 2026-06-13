"""Quick read-only peek at what's in the pipeline DB. For manual inspection.

    python -m scripts.peek_db   (or: uv run python scripts/peek_db.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a loose script: ensure src/ is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func

from db.models import RawTrend, Script, Trend, Video
from db.session import session_scope


def main() -> None:
    with session_scope() as session:
        raw_count = session.query(func.count(RawTrend.id)).scalar()
        trend_count = session.query(func.count(Trend.id)).scalar()
        script_count = session.query(func.count(Script.id)).scalar()
        video_count = session.query(func.count(Video.id)).scalar()

        print(
            f"raw_trends: {raw_count}   trends: {trend_count}   "
            f"scripts: {script_count}   videos: {video_count}\n"
        )

        videos = session.query(Video).all()
        if videos:
            print("Videos:")
            for v in videos:
                print(f"  [{v.status.value}] ({v.provider})  script={v.script_id}  {v.video_url}")
            print()

        print("Top 10 raw trends by views:")
        rows = session.query(RawTrend).all()
        rows.sort(key=lambda r: (r.metrics_json or {}).get("views", 0) or 0, reverse=True)
        for r in rows[:10]:
            views = (r.metrics_json or {}).get("views", 0) or 0
            # Strip non-ASCII so the Windows console (cp1252) never chokes on emoji
            title = r.title[:65].encode("ascii", "replace").decode("ascii")
            print(f"  {views:>12,}  [{r.source.value}]  {title}")


if __name__ == "__main__":
    main()
