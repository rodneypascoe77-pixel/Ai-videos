"""Tests for Phase 7 feedback loop (stub analytics — no real YouTube calls)."""

from __future__ import annotations

from db.models import (
    CategoryStat,
    PerformanceSnapshot,
    Post,
    PostStatus,
    Script,
    Trend,
    Video,
    VideoStatus,
)
from db.session import session_scope
from feedback.aggregator import aggregate, category_hints
from feedback.collector import collect
from feedback.provider import (
    AnalyticsError,
    AnalyticsProvider,
    Metrics,
    StubAnalyticsProvider,
    get_analytics_provider,
)


def _seed_posted_video(category: str, platform_video_id: str) -> int:
    with session_scope() as session:
        t = Trend(name=f"trend-{category}", category=category, is_ai_trend=True)
        session.add(t)
        session.flush()
        s = Script(trend_id=t.id, title="x", script_text="...")
        session.add(s)
        session.flush()
        v = Video(script_id=s.id, provider="stub", status=VideoStatus.posted)
        session.add(v)
        session.flush()
        p = Post(
            video_id=v.id,
            title="x",
            status=PostStatus.posted,
            platform_video_id=platform_video_id,
        )
        session.add(p)
        session.flush()
        return p.id


def test_stub_provider_deterministic():
    p = StubAnalyticsProvider()
    a = p.fetch("abc")
    b = p.fetch("abc")
    assert a.views == b.views
    assert a.likes == a.views // 20


def test_get_provider_stub_offline(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "true")
    assert isinstance(get_analytics_provider(), StubAnalyticsProvider)


def test_collect_writes_snapshots():
    _seed_posted_video("creature-vlog", "vid_a")
    _seed_posted_video("pov-skit", "vid_b")

    n = collect(provider=StubAnalyticsProvider())
    assert n == 2
    with session_scope() as session:
        assert session.query(PerformanceSnapshot).count() == 2


def test_collect_skips_failures():
    _seed_posted_video("creature-vlog", "vid_a")

    class Boom(AnalyticsProvider):
        name = "boom"

        def fetch(self, platform_video_id):
            raise AnalyticsError("nope")

    n = collect(provider=Boom())
    assert n == 0
    with session_scope() as session:
        assert session.query(PerformanceSnapshot).count() == 0


def test_aggregate_builds_category_stats():
    post_a = _seed_posted_video("creature-vlog", "vid_a")
    post_b = _seed_posted_video("pov-skit", "vid_b")

    # Two snapshots for creature-vlog post (newest should win), one for pov-skit
    with session_scope() as session:
        session.add(PerformanceSnapshot(post_id=post_a, views=10, likes=1, comments=0))
        session.add(PerformanceSnapshot(post_id=post_a, views=500, likes=50, comments=10))
        session.add(PerformanceSnapshot(post_id=post_b, views=100, likes=5, comments=1))

    stats = aggregate()
    assert stats["creature-vlog"]["avg_views"] == 500.0   # newest snapshot, not 10
    assert stats["creature-vlog"]["avg_engagement"] == 60.0  # 50 likes + 10 comments
    assert stats["pov-skit"]["avg_views"] == 100.0

    with session_scope() as session:
        cv = session.get(CategoryStat, "creature-vlog")
        assert cv.total_views == 500
        assert cv.n_videos == 1


def test_aggregate_no_snapshots_is_empty():
    assert aggregate() == {}


def test_category_hints_empty_on_cold_start():
    assert category_hints() == ""


def test_category_hints_summarizes_after_data():
    post_a = _seed_posted_video("creature-vlog", "vid_a")
    with session_scope() as session:
        session.add(PerformanceSnapshot(post_id=post_a, views=9000, likes=400, comments=50))
    aggregate()

    hint = category_hints()
    assert "creature-vlog" in hint
    assert "9000 views" in hint


def test_runner_collect_then_aggregate(monkeypatch):
    import feedback.runner as runner

    _seed_posted_video("creature-vlog", "vid_a")
    monkeypatch.setattr(runner, "init_db", lambda: None)

    summary = runner.run()
    assert summary["snapshots"] == 1
    assert "creature-vlog" in summary["categories"]


def test_metrics_dataclass_defaults():
    m = Metrics()
    assert m.views == 0 and m.likes == 0 and m.comments == 0


def test_classifier_uses_performance_hint(monkeypatch):
    # The classifier should fold the learned hint into its prompt.
    from classification.classifier import TrendClassifier
    from classification.schema import ClassificationResult

    post_a = _seed_posted_video("creature-vlog", "vid_a")
    with session_scope() as session:
        session.add(PerformanceSnapshot(post_id=post_a, views=12345, likes=600, comments=70))
    aggregate()

    clf = TrendClassifier.__new__(TrendClassifier)
    clf.model = "claude-sonnet-4-6"

    captured = {}

    class FakeMessages:
        def parse(self, **kwargs):
            captured["content"] = kwargs["messages"][0]["content"]
            out = type("R", (), {"parsed_output": ClassificationResult(trends=[])})
            return out

    clf.client = type("C", (), {"messages": FakeMessages()})()
    clf._call_model("evidence here", 1)

    assert "creature-vlog" in captured["content"]
    assert "12345 views" in captured["content"]
