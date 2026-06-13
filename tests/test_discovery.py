"""Tests for the discovery cycle and scheduler wiring (no real APIs)."""

from __future__ import annotations

import discovery
from config import get_settings


def test_run_cycle_fetches_then_classifies(monkeypatch):
    calls = []

    def fake_run_all():
        calls.append("fetch")
        return {"youtube": 3, "reddit": 2, "google_trends": 0}

    class FakeClassifier:
        def run(self):
            calls.append("classify")
            return {"raw_processed": 5, "trends_new": 2, "trends_updated": 1}

    monkeypatch.setattr(discovery, "run_all", fake_run_all)
    monkeypatch.setattr(discovery, "TrendClassifier", lambda: FakeClassifier())

    summary = discovery.run_cycle()

    # Fetch must run before classify
    assert calls == ["fetch", "classify"]
    assert summary["fetched_youtube"] == 3
    assert summary["trends_new"] == 2
    assert summary["trends_updated"] == 1


def test_run_cycle_survives_classification_failure(monkeypatch):
    def fake_run_all():
        return {"youtube": 1}

    class ExplodingClassifier:
        def run(self):
            raise RuntimeError("API down")

    monkeypatch.setattr(discovery, "run_all", fake_run_all)
    monkeypatch.setattr(discovery, "TrendClassifier", lambda: ExplodingClassifier())

    # Should NOT raise — fetched evidence is retained for the next cycle
    summary = discovery.run_cycle()
    assert summary["fetched_youtube"] == 1
    assert summary["trends_new"] == 0


def test_scheduler_registers_discovery_job(monkeypatch):
    monkeypatch.setenv("DISCOVERY_INTERVAL_HOURS", "6")
    # Settings is cached as a dataclass per-call, so a fresh load picks up the env
    import scheduler

    # build_scheduler() does NOT start the scheduler (starting a BlockingScheduler
    # would block). get_job reads pending jobs on a non-running scheduler.
    sched = scheduler.build_scheduler()
    job = sched.get_job("trend_discovery")
    assert job is not None
    assert job.func is discovery.run_cycle
    # Interval reflects the env override
    assert get_settings().DISCOVERY_INTERVAL_HOURS == 6.0
