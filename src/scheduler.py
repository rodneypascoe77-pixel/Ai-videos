"""APScheduler entry-point — runs trend discovery on a fixed interval.

Phase 1 schedules a single job (fetch + classify). Later phases register
additional jobs (script gen, video gen, QA, posting) on this same scheduler.

Run:
    python -m scheduler
"""

from __future__ import annotations

import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from config import get_settings
from db.init import init_db
from db.logging import get_logger
from discovery import run_cycle

log = get_logger("scheduler")


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_cycle,
        trigger="interval",
        hours=settings.DISCOVERY_INTERVAL_HOURS,
        id="trend_discovery",
        replace_existing=True,
        max_instances=1,            # never overlap cycles
        coalesce=True,              # if we fell behind, run once not N times
        next_run_time=datetime.now(timezone.utc),  # run immediately on startup
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

    log.info(f"Scheduler starting; trend discovery every {settings.DISCOVERY_INTERVAL_HOURS}h")
    scheduler.start()


if __name__ == "__main__":
    main()
