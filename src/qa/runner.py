"""Phase 4 orchestration: QA all videos that finished generation.

Processes every Video in status `completed`, marking each qa_passed or qa_failed.

    python -m qa.runner
"""

from __future__ import annotations

from db.init import init_db
from db.logging import get_logger
from db.models import Video, VideoStatus
from db.session import session_scope
from qa.checker import QualityChecker

log = get_logger("qa.runner")


def completed_video_ids(limit: int | None = None) -> list[int]:
    with session_scope() as session:
        q = (
            session.query(Video.id)
            .filter(Video.status == VideoStatus.completed)
            .order_by(Video.id)
        )
        if limit:
            q = q.limit(limit)
        return [r[0] for r in q.all()]


def run(limit: int | None = None) -> dict[str, int]:
    init_db()
    video_ids = completed_video_ids(limit)
    if not video_ids:
        log.info("No completed videos awaiting QA")
        return {"checked": 0, "passed": 0, "failed": 0}

    checker = QualityChecker()
    totals = {"checked": 0, "passed": 0, "failed": 0}
    for vid in video_ids:
        try:
            ok = checker.run_for_video(vid)
        except Exception as exc:
            log.error("QA crashed for video", video_id=vid, error=str(exc))
            continue
        totals["checked"] += 1
        totals["passed" if ok else "failed"] += 1

    log.info(
        f"QA complete: {totals['checked']} checked, "
        f"{totals['passed']} passed, {totals['failed']} failed"
    )
    return totals


if __name__ == "__main__":
    summary = run()
    print("\nQA summary:")
    for k, v in summary.items():
        print(f"  {k:>10}: {v}")
