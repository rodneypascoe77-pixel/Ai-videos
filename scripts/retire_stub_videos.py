"""Retire leftover stub videos so live posting doesn't get stuck on them.

Stub videos have no downloadable file, so the live YouTube publisher can't upload
them. Mark any qa_passed stub videos as qa_failed so the posting runner skips them.

    uv run python scripts/retire_stub_videos.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.models import Video, VideoStatus
from db.session import session_scope


def main() -> None:
    with session_scope() as session:
        rows = (
            session.query(Video)
            .filter(Video.provider == "stub", Video.status == VideoStatus.qa_passed)
            .all()
        )
        for v in rows:
            v.status = VideoStatus.qa_failed
        print(f"Retired {len(rows)} stub videos (qa_passed -> qa_failed).")


if __name__ == "__main__":
    main()
