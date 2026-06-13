"""APScheduler entry-point — runs trend discovery on a fixed interval.

Phase 1 schedules a single job (fetch + classify). Later phases register
additional jobs (script gen, video gen, QA, posting) on this same scheduler.

Run:
    python -m scheduler
"""

from __future__ import annotations

import signal
import sys
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from config import get_settings
from db.init import init_db
from db.logging import get_logger
from discovery import run_cycle
from generation.runner import run as run_script_generation
from posting.runner import run as run_posting
from qa.runner import run as run_qa
from video.runner import run as run_video_generation

log = get_logger("scheduler")


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    interval = settings.DISCOVERY_INTERVAL_HOURS
    scheduler = BlockingScheduler(timezone="UTC")

    now = datetime.now(timezone.utc)
    # Phase 1: fetch + classify trends.
    scheduler.add_job(
        run_cycle,
        trigger="interval",
        hours=interval,
        id="trend_discovery",
        replace_existing=True,
        max_instances=1,            # never overlap cycles
        coalesce=True,              # if we fell behind, run once not N times
        next_run_time=now,          # run immediately on startup
    )
    # Phase 2: generate + select scripts for newly-classified trends. Offset a few
    # minutes after discovery so the first run has fresh trends to work with.
    scheduler.add_job(
        run_script_generation,
        trigger="interval",
        hours=interval,
        id="script_generation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now + timedelta(minutes=5),
    )
    # Phase 3: generate videos for queued trends' selected scripts. Offset further
    # so scripts exist first. In live mode this spends money — keep it conservative.
    scheduler.add_job(
        run_video_generation,
        trigger="interval",
        hours=interval,
        id="video_generation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now + timedelta(minutes=10),
    )
    # Phase 4: QA the freshly-generated videos. Offset after video generation.
    scheduler.add_job(
        run_qa,
        trigger="interval",
        hours=interval,
        id="video_qa",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now + timedelta(minutes=15),
    )
    # Phase 5: post one QA-passed video to YouTube, on its own (slower) cadence.
    scheduler.add_job(
        run_posting,
        trigger="interval",
        hours=settings.POST_INTERVAL_HOURS,
        id="youtube_posting",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=now + timedelta(minutes=20),
    )
    return scheduler


def main() -> None:
    init_db()
    settings = get_settings()
    scheduler = build_scheduler()

    def _shutdown(signum, frame):
        log.info("Shutdown signal received; stopping scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info(
        "Scheduler starting; discovery + script generation every "
        f"{settings.DISCOVERY_INTERVAL_HOURS}h"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
