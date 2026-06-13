"""Tests for Phase 4 video QA (no network — fetch is stubbed)."""

from __future__ import annotations

import struct

from db.models import Script, Trend, Video, VideoStatus
from db.session import session_scope
from qa.checker import QualityChecker
from qa.mp4 import is_mp4, parse_duration_seconds


def _make_mp4(duration_s: float, timescale: int = 600, pad: int = 0) -> bytes:
    """Build a minimal byte blob with an ftyp marker and a v0 mvhd box."""
    ftyp = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
    dur = int(duration_s * timescale)
    mvhd = (
        b"mvhd"
        + bytes([0])           # version 0
        + b"\x00\x00\x00"      # flags
        + b"\x00\x00\x00\x00"  # creation
        + b"\x00\x00\x00\x00"  # modification
        + struct.pack(">I", timescale)
        + struct.pack(">I", dur)
    )
    return ftyp + mvhd + (b"\x00" * pad)


def test_is_mp4_and_duration_parse():
    data = _make_mp4(5.0)
    assert is_mp4(data)
    assert abs(parse_duration_seconds(data) - 5.0) < 0.01


def test_duration_none_when_no_mvhd():
    assert parse_duration_seconds(b"not an mp4 at all") is None


def _make_completed_video(provider="runway", url="https://cdn.example/x.mp4") -> int:
    with session_scope() as session:
        t = Trend(name="T", is_ai_trend=True)
        session.add(t)
        session.flush()
        s = Script(trend_id=t.id, title="x", script_text="...")
        session.add(s)
        session.flush()
        v = Video(
            script_id=s.id,
            provider=provider,
            video_url=url,
            status=VideoStatus.completed,
            duration_seconds=5,
        )
        session.add(v)
        session.flush()
        return v.id


def _checker_with_bytes(data: bytes, tmp_path) -> QualityChecker:
    checker = QualityChecker(video_dir=tmp_path)
    checker._download = lambda url, dest: (dest.write_bytes(data), data)[1]
    return checker


def test_check_passes_valid_video(tmp_path):
    vid = _make_completed_video()
    checker = _checker_with_bytes(_make_mp4(5.0, pad=60_000), tmp_path)

    ok = checker.run_for_video(vid)
    assert ok is True
    with session_scope() as session:
        v = session.get(Video, vid)
        assert v.status == VideoStatus.qa_passed
        assert v.local_path is not None
        assert v.duration_seconds == 5


def test_check_fails_tiny_file(tmp_path):
    vid = _make_completed_video()
    checker = _checker_with_bytes(_make_mp4(5.0, pad=10), tmp_path)  # too small

    ok = checker.run_for_video(vid)
    assert ok is False
    with session_scope() as session:
        assert session.get(Video, vid).status == VideoStatus.qa_failed


def test_check_fails_wrong_duration(tmp_path):
    vid = _make_completed_video()
    # 60s clip when we expected ~5s -> out of tolerance
    checker = _checker_with_bytes(_make_mp4(60.0, pad=60_000), tmp_path)

    ok = checker.run_for_video(vid)
    assert ok is False
    with session_scope() as session:
        v = session.get(Video, vid)
        assert v.status == VideoStatus.qa_failed
        assert "duration" in v.qa_notes


def test_check_fails_non_mp4(tmp_path):
    vid = _make_completed_video()
    checker = _checker_with_bytes(b"X" * 60_000, tmp_path)  # big enough but not mp4

    ok = checker.run_for_video(vid)
    assert ok is False
    with session_scope() as session:
        assert session.get(Video, vid).status == VideoStatus.qa_failed


def test_stub_video_auto_passes(tmp_path):
    vid = _make_completed_video(provider="stub", url="https://stub.local/videos/abc.mp4")
    checker = QualityChecker(video_dir=tmp_path)  # no _download override needed

    ok = checker.run_for_video(vid)
    assert ok is True
    with session_scope() as session:
        assert session.get(Video, vid).status == VideoStatus.qa_passed


def test_runner_processes_completed(monkeypatch, tmp_path):
    import qa.runner as runner

    vid = _make_completed_video(provider="stub", url="https://stub.local/videos/abc.mp4")
    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "QualityChecker", lambda: QualityChecker(video_dir=tmp_path))

    totals = runner.run()
    assert totals == {"checked": 1, "passed": 1, "failed": 0}
    with session_scope() as session:
        assert session.get(Video, vid).status == VideoStatus.qa_passed
