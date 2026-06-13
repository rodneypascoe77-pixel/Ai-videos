"""Tests for the Phase 6 dashboard (FastAPI TestClient, seeded DB)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app
from db.models import (
    Post,
    PostStatus,
    Script,
    ScriptStatus,
    Trend,
    TrendStatus,
    Video,
    VideoStatus,
)
from db.session import session_scope


@pytest.fixture
def client():
    return TestClient(app)


def _seed():
    with session_scope() as session:
        t = Trend(
            name="Bigfoot vlog",
            summary="Bigfoot films his day",
            category="creature-vlog",
            is_ai_trend=True,
            overall_score=79.7,
            momentum_score=80,
            saturation_score=20,
            fit_score=90,
            status=TrendStatus.used,
        )
        session.add(t)
        session.flush()
        s = Script(
            trend_id=t.id,
            title="Bigfoot Has One Bad Day",
            premise="stress-eats, goes viral",
            script_text="...",
            status=ScriptStatus.used,
            quality_score=91,
            selection_rank=1,
        )
        session.add(s)
        session.flush()
        v = Video(
            script_id=s.id,
            provider="runway",
            status=VideoStatus.posted,
            duration_seconds=5,
            qa_notes="all checks ok",
            video_url="https://cdn/x.mp4",
        )
        session.add(v)
        session.flush()
        session.add(
            Post(
                video_id=v.id,
                title="Bigfoot Has One Bad Day",
                privacy="private",
                status=PostStatus.posted,
                post_url="https://youtube.com/watch?v=abc",
            )
        )
        return t.id


def test_api_stats_reflects_data(client):
    _seed()
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["trends"] == 1
    assert data["ai_trends"] == 1
    assert data["scripts"] == 1
    assert data["videos"] == 1
    assert data["posts"] == 1


def test_overview_page(client):
    _seed()
    r = client.get("/")
    assert r.status_code == 200
    assert "Pipeline Overview" in r.text
    assert "Bigfoot Has One Bad Day" in r.text  # recent post title


def test_trends_page_lists_trend(client):
    _seed()
    r = client.get("/trends")
    assert r.status_code == 200
    assert "Bigfoot vlog" in r.text
    assert "79.7" in r.text  # overall score


def test_trend_detail_shows_scripts(client):
    trend_id = _seed()
    r = client.get(f"/trends/{trend_id}")
    assert r.status_code == 200
    assert "Bigfoot Has One Bad Day" in r.text
    assert "Scripts" in r.text


def test_trend_detail_404(client):
    r = client.get("/trends/999999")
    assert r.status_code == 404
    assert "not found" in r.text.lower()


def test_videos_page(client):
    _seed()
    r = client.get("/videos")
    assert r.status_code == 200
    assert "runway" in r.text


def test_posts_page_has_youtube_link(client):
    _seed()
    r = client.get("/posts")
    assert r.status_code == 200
    assert "youtube.com/watch?v=abc" in r.text


def test_logs_page_and_filter(client):
    _seed()
    assert client.get("/logs").status_code == 200
    assert client.get("/logs?level=error").status_code == 200


def test_empty_db_pages_still_render(client):
    # No seed — every page should render without error.
    for path in ("/", "/trends", "/videos", "/posts", "/logs"):
        assert client.get(path).status_code == 200
