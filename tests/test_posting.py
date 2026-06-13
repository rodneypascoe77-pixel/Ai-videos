"""Tests for Phase 5 YouTube posting (stub publisher — no real uploads)."""

from __future__ import annotations

import pytest

from db.models import (
    Post,
    PostStatus,
    Script,
    Trend,
    Video,
    VideoStatus,
)
from db.session import session_scope
from posting.metadata import build_metadata
from posting.publisher import (
    Publisher,
    PublisherError,
    StubPublisher,
    get_publisher,
)


def _seed_qa_passed_video(provider="stub") -> int:
    with session_scope() as session:
        t = Trend(name="Bigfoot vlog", is_ai_trend=True)
        session.add(t)
        session.flush()
        s = Script(
            trend_id=t.id,
            title="Bigfoot Has One Bad Day",
            premise="Bigfoot stress-eats and goes viral",
            script_text="...",
        )
        session.add(s)
        session.flush()
        v = Video(
            script_id=s.id,
            provider=provider,
            video_url="https://stub.local/x.mp4",
            local_path=None,
            status=VideoStatus.qa_passed,
        )
        session.add(v)
        session.flush()
        return v.id


def test_build_metadata_limits_and_tags():
    s = Script(title="A" * 200, premise="funny premise about bigfoot", script_text="...")
    t = Trend(name="Bigfoot vlog")
    meta = build_metadata(s, t)
    assert len(meta.title) <= 100
    assert meta.category_id == "23"  # Comedy
    assert "ai" in [x.lower() for x in meta.tags]
    assert "#shorts" in meta.description


def test_get_publisher_stub_in_offline(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "true")
    assert isinstance(get_publisher(), StubPublisher)


def test_stub_publish_is_deterministic():
    from posting.metadata import PostMetadata

    p = StubPublisher()
    meta = PostMetadata(title="T", description="d", tags=["a"])
    a = p.publish(None, meta, "private")
    b = p.publish(None, meta, "private")
    assert a.platform_video_id == b.platform_video_id
    assert a.post_url.startswith("https://youtube.com/watch?v=")


def test_runner_posts_and_marks_video(monkeypatch):
    import posting.runner as runner

    vid = _seed_qa_passed_video()
    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "get_publisher", lambda: StubPublisher())

    totals = runner.run(max_posts=5)
    assert totals == {"posted": 1, "failed": 0}

    with session_scope() as session:
        video = session.get(Video, vid)
        assert video.status == VideoStatus.posted
        post = session.query(Post).filter_by(video_id=vid).one()
        assert post.status == PostStatus.posted
        assert post.platform_video_id
        assert post.post_url


def test_runner_skips_already_posted(monkeypatch):
    import posting.runner as runner

    vid = _seed_qa_passed_video()
    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "get_publisher", lambda: StubPublisher())

    runner.run(max_posts=5)            # first post
    totals = runner.run(max_posts=5)   # nothing left to post
    assert totals == {"posted": 0, "failed": 0}

    with session_scope() as session:
        assert session.query(Post).filter_by(video_id=vid).count() == 1


def test_runner_records_failure(monkeypatch):
    import posting.runner as runner

    vid = _seed_qa_passed_video()

    class FailingPublisher(Publisher):
        name = "boom"

        def publish(self, video_path, meta, privacy):
            raise PublisherError("upload exploded")

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "get_publisher", lambda: FailingPublisher())

    totals = runner.run(max_posts=5)
    assert totals == {"posted": 0, "failed": 1}

    with session_scope() as session:
        post = session.query(Post).filter_by(video_id=vid).one()
        assert post.status == PostStatus.failed
        assert "exploded" in post.error
        # Video NOT marked posted on failure
        assert session.get(Video, vid).status == VideoStatus.qa_passed


def test_only_qa_passed_are_postable():
    import posting.runner as runner

    # a completed-but-not-QA'd video should not be postable
    with session_scope() as session:
        t = Trend(name="T", is_ai_trend=True)
        session.add(t)
        session.flush()
        s = Script(trend_id=t.id, title="x", script_text="...")
        session.add(s)
        session.flush()
        session.add(Video(script_id=s.id, provider="stub", status=VideoStatus.completed))

    assert runner.postable_video_ids(10) == []


def test_get_publisher_youtube_when_live(monkeypatch):
    monkeypatch.setenv("OFFLINE_MODE", "false")
    from posting.publisher import YouTubePublisher

    assert isinstance(get_publisher(), YouTubePublisher)


def test_youtube_publish_errors_without_token(monkeypatch, tmp_path):
    from posting.metadata import PostMetadata
    from posting.publisher import YouTubePublisher

    pub = YouTubePublisher(token_file=str(tmp_path / "missing_token.json"))
    with pytest.raises(PublisherError):
        pub.publish(str(tmp_path / "v.mp4"), PostMetadata("t", "d", ["x"]), "private")
