"""Generate ONE real video for the top trend's rank-1 script.

Forces the live provider (expects OFFLINE_MODE=false in the environment) and
generates a single clip — used to verify the RunwayML integration for the cost
of one video.

    OFFLINE_MODE=false uv run python scripts/run_one_video.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.models import Script, Trend, Video
from db.session import session_scope
from video.generator import VideoGenerator
from video.provider import get_provider


def main() -> None:
    provider = get_provider()
    print(f"Provider: {provider.name}")
    if provider.name != "runway":
        print("Not in live mode (set OFFLINE_MODE=false). Aborting to avoid a stub run.")
        return

    with session_scope() as session:
        trend = (
            session.query(Trend)
            .filter(Trend.is_ai_trend.is_(True))
            .order_by(Trend.overall_score.desc())
            .first()
        )
        if trend is None:
            print("No trend found.")
            return
        # rank-1 script for that trend (selected or already used)
        script = (
            session.query(Script)
            .filter(Script.trend_id == trend.id, Script.selection_rank == 1)
            .first()
        )
        if script is None:
            print("No rank-1 script found.")
            return
        script_id = script.id
        title = script.title.encode("ascii", "replace").decode("ascii")
        trend_name = trend.name.encode("ascii", "replace").decode("ascii")

    print(f"Trend: {trend_name}")
    print(f"Script #{script_id}: {title}")
    print("Submitting to RunwayML (text->image, then image->video). This takes a minute or two...")

    gen = VideoGenerator(provider=provider)
    video_id = gen.generate_for_script(script_id)

    with session_scope() as session:
        if video_id is None:
            v = (
                session.query(Video)
                .filter(Video.script_id == script_id)
                .order_by(Video.id.desc())
                .first()
            )
            print("\nFAILED.")
            if v is not None:
                print("Error:", (v.error or "")[:500])
            return
        v = session.get(Video, video_id)
        print("\nSUCCESS")
        print("Status:   ", v.status.value)
        print("Provider: ", v.provider, "| job:", v.provider_job_id)
        print("Video URL:", v.video_url)


if __name__ == "__main__":
    main()
