"""Validate a generated video against deterministic quality checks.

Real videos are downloaded once (to data/videos/) and checked for: a valid MP4
container, a sane file size, and a duration within tolerance of what we asked the
provider for. Stub videos (offline mode) can't be downloaded, so they auto-pass
with a note — keeping the whole pipeline runnable for free.

No AI cost: all checks are byte-level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import DATA_DIR, get_settings
from db.logging import get_logger
from db.models import Video, VideoStatus
from db.session import session_scope
from qa.mp4 import is_mp4, parse_duration_seconds

log = get_logger("qa.checker")

_MIN_BYTES = 50 * 1024            # 50 KB — anything smaller isn't a real clip
_MAX_BYTES = 200 * 1024 * 1024   # 200 MB — sanity ceiling
_DURATION_TOLERANCE = 0.5        # allow expected*0.5 .. expected*2.0


@dataclass
class QAReport:
    passed: bool
    checks: list[dict] = field(default_factory=list)
    local_path: str | None = None
    duration_seconds: float | None = None

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append({"check": name, "passed": ok, "detail": detail})

    def summary(self) -> str:
        return "; ".join(
            f"{c['check']}={'ok' if c['passed'] else 'FAIL'} ({c['detail']})" for c in self.checks
        )


class QualityChecker:
    def __init__(self, video_dir: Path | None = None) -> None:
        self.video_dir = video_dir or (DATA_DIR / "videos")

    def _download(self, url: str, dest: Path) -> bytes:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
        dest.write_bytes(data)
        return data

    def check(self, video: Video) -> QAReport:
        """Run all checks for a video object (detached or live). Returns a QAReport."""
        report = QAReport(passed=True)
        settings = get_settings()

        # 0) Must have completed with a URL.
        if video.status != VideoStatus.completed or not video.video_url:
            report.add(
                "has_output", False,
                f"status={video.status.value}, has_url={bool(video.video_url)}",
            )
            report.passed = False
            return report
        report.add("has_output", True, "completed with url")

        # Stub videos can't be downloaded — auto-pass the content checks.
        if video.provider == "stub" or video.video_url.startswith("https://stub.local/"):
            report.add("stub", True, "stub video — content checks skipped")
            report.duration_seconds = float(video.duration_seconds or 0)
            return report

        # 1) Download.
        dest = self.video_dir / f"video_{video.id}.mp4"
        try:
            data = self._download(video.video_url, dest)
        except Exception as exc:
            report.add("download", False, str(exc)[:200])
            report.passed = False
            return report
        report.add("download", True, f"{len(data)} bytes")
        report.local_path = str(dest)

        # 2) Size sanity.
        size_ok = _MIN_BYTES <= len(data) <= _MAX_BYTES
        report.add("size", size_ok, f"{len(data)} bytes")
        report.passed &= size_ok

        # 3) Valid MP4 container.
        mp4_ok = is_mp4(data)
        report.add("mp4_container", mp4_ok, "ftyp present" if mp4_ok else "no ftyp box")
        report.passed &= mp4_ok

        # 4) Duration within tolerance of what we requested.
        duration = parse_duration_seconds(data)
        report.duration_seconds = duration
        expected = float(settings.VIDEO_DURATION)
        if duration is None:
            report.add("duration", False, "could not parse duration")
            report.passed = False
        else:
            lo, hi = expected * _DURATION_TOLERANCE, expected * (1 / _DURATION_TOLERANCE)
            dur_ok = lo <= duration <= hi
            report.add("duration", dur_ok, f"{duration:.2f}s (expected ~{expected:.0f}s)")
            report.passed &= dur_ok

        return report

    def run_for_video(self, video_id: int) -> bool:
        """Check one video and persist the verdict. Returns whether it passed."""
        with session_scope() as session:
            video = session.get(Video, video_id)
            if video is None:
                raise ValueError(f"Video {video_id} not found")
            session.expunge(video)

        report = self.check(video)

        with session_scope() as session:
            v = session.get(Video, video_id)
            v.status = VideoStatus.qa_passed if report.passed else VideoStatus.qa_failed
            v.qa_notes = report.summary()[:2000]
            v.qa_checks = {"checks": report.checks}
            if report.local_path:
                v.local_path = report.local_path
            if report.duration_seconds is not None:
                v.duration_seconds = int(round(report.duration_seconds))
            v.completed_at = v.completed_at or datetime.now(timezone.utc)

        log.info(
            f"QA {'passed' if report.passed else 'FAILED'} for video {video_id}",
            video_id=video_id,
        )
        return report.passed
