"""Tests for Phase 3 video generation (stub provider — no real Runway calls)."""

from __future__ import annotations

import pytest

from db.models import Script, ScriptStatus, Trend, TrendStatus, Video, VideoStatus
from db.session import session_scope
from video.generator import VideoGenerator
from video.prompt import build_prompts
from video.provider import (
    StubVideoProvider,
    VideoProvider,
    VideoProviderError,
    VideoResult,
    get_provider,
)


def _make_trend_with_selected_script(rank: int = 1) -> tuple[int, int]:
    with session_scope() as session:
        t = Trend(name="Bigfoot vlog", is_ai_trend=True, status=TrendStatus.queued,
                  overall_score=80)
        session.add(t)
        session.flush()
        s = Script(
            trend_id=t.id,
            title="Bigfoot orders coffee",
            premise="Bigfoot tries a drive-thru on foot",
            script_text="...",
            status=ScriptStatus.selected,
            selection_rank=rank,
        )
        session.add(s)
        session.flush()
        return t.id, s.id


def test_get_provider_returns_stub_in_offline_mode(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "true")
    assert isinstance(get_provider(), StubVideoProvider)


def test_get_provider_errors_live_without_key(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    with pytest.raises(VideoProviderError):
        get_provider()


def test_stub_provider_is_deterministic():
    p = StubVideoProvider()
    a = p.generate("scene", "motion")
    b = p.generate("scene", "motion")
    assert a.video_url == b.video_url
    assert a.video_url.endswith(".mp4")


def test_build_prompts_uses_premise():
    s = Script(title="T", premise="Bigfoot orders coffee", script_text="...")
    image_prompt, motion_prompt = build_prompts(s)
    assert "Bigfoot orders coffee" in image_prompt
    assert "Bigfoot orders coffee" in motion_prompt


def test_generate_for_script_completes_and_marks_used():
    _, script_id = _make_trend_with_selected_script()
    gen = VideoGenerator(provider=StubVideoProvider())

    video_id = gen.generate_for_script(script_id)
    assert video_id is not None

    with session_scope() as session:
        video = session.get(Video, video_id)
        assert video.status == VideoStatus.completed
        assert video.video_url
        assert video.provider == "stub"
        # Source script marked used
        assert session.get(Script, script_id).status == ScriptStatus.used


def test_generate_records_failure(monkeypatch):
    _, script_id = _make_trend_with_selected_script()

    class FailingProvider(VideoProvider):
        name = "boom"

        def generate(self, image_prompt, motion_prompt):
            raise VideoProviderError("kaboom")

    gen = VideoGenerator(provider=FailingProvider())
    video_id = gen.generate_for_script(script_id)
    assert video_id is None

    with session_scope() as session:
        video = session.query(Video).filter_by(script_id=script_id).one()
        assert video.status == VideoStatus.failed
        assert "kaboom" in video.error
        # Script NOT marked used on failure
        assert session.get(Script, script_id).status == ScriptStatus.selected


def test_runner_processes_queued_trend(monkeypatch):
    import video.runner as runner

    trend_id, _ = _make_trend_with_selected_script()

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "get_provider", lambda: StubVideoProvider())

    totals = runner.run(max_trends=5)
    assert totals["trends_processed"] == 1
    assert totals["videos_completed"] == 1
    assert totals["videos_failed"] == 0

    with session_scope() as session:
        assert session.get(Trend, trend_id).status == TrendStatus.used


def test_runner_no_queued_trends_is_noop(monkeypatch):
    import video.runner as runner

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "get_provider", lambda: StubVideoProvider())
    totals = runner.run()
    assert totals == {"trends_processed": 0, "videos_completed": 0, "videos_failed": 0}


def test_videoresult_shape():
    r = VideoResult(video_url="x", provider_job_id="j", duration_seconds=5)
    assert r.video_url == "x" and r.duration_seconds == 5
