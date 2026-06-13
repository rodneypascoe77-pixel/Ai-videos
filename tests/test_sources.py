"""Tests for source fetch -> persist, with all HTTP mocked."""

from __future__ import annotations

from db.models import RawTrend, Source
from db.session import session_scope
from sources.base import FetchedItem, save_items


def test_save_items_persists_raw_trends():
    items = [
        FetchedItem(
            source=Source.youtube,
            title="Bigfoot vlogs his morning routine",
            url="https://youtube.com/watch?v=abc",
            metrics={"views": 1_200_000, "velocity": 5000.0},
        ),
        FetchedItem(source=Source.reddit, title="New AI video tool dropped"),
    ]
    ids = save_items(items)
    assert len(ids) == 2

    with session_scope() as session:
        rows = session.query(RawTrend).all()
        assert {r.source for r in rows} == {Source.youtube, Source.reddit}
        yt = next(r for r in rows if r.source == Source.youtube)
        assert yt.metrics_json["views"] == 1_200_000


def test_save_items_empty_is_noop():
    assert save_items([]) == []


def test_reddit_skips_without_credentials(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    from sources.reddit import RedditSource

    src = RedditSource()
    assert src.configured is False
    assert src.fetch() == []


def test_youtube_fetch_parses_and_persists(monkeypatch):
    from sources.youtube import YouTubeSource

    search_payload = [
        {"id": {"videoId": "abc"}},
        {"id": {"videoId": "def"}},
    ]
    stats_payload = {
        "abc": {
            "snippet": {
                "title": "AI Bigfoot vlog",
                "description": "funny",
                "channelTitle": "AIChannel",
                "publishedAt": "2026-06-10T00:00:00Z",
            },
            "statistics": {"viewCount": "500000", "likeCount": "1000", "commentCount": "50"},
        },
        "def": {
            "snippet": {"title": "AI cat vlog", "publishedAt": "2026-06-11T00:00:00Z"},
            "statistics": {"viewCount": "10000"},
        },
    }

    src = YouTubeSource(api_key="fake", per_query=5)
    # Only the first query returns results; rest empty to keep dedup simple.
    calls = {"search": 0}

    def fake_search(query, published_after):
        calls["search"] += 1
        return search_payload if calls["search"] == 1 else []

    monkeypatch.setattr(src, "_search", fake_search)
    monkeypatch.setattr(src, "_stats", lambda ids: stats_payload)

    items = src.fetch()
    assert len(items) == 2
    abc = next(i for i in items if "Bigfoot" in i.title)
    assert abc.metrics["views"] == 500000
    assert abc.metrics["velocity"] > 0

    ids = save_items(items)
    assert len(ids) == 2


def test_velocity_handles_missing_timestamp():
    from sources.youtube import _velocity

    assert _velocity(1000, None) == 0.0
    assert _velocity(0, "2026-06-01T00:00:00Z") == 0.0
