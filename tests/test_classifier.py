"""Tests for the trend classifier (Anthropic client fully mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from classification.classifier import TrendClassifier, compute_overall
from classification.schema import ClassificationResult, ClassifiedTrend
from db.models import RawTrend, Source, Trend, TrendStatus
from db.session import session_scope


def test_compute_overall_inverts_saturation():
    # High saturation should LOWER the score relative to low saturation.
    low_sat = compute_overall(momentum=80, fit=80, saturation=10)
    high_sat = compute_overall(momentum=80, fit=80, saturation=90)
    assert low_sat > high_sat

    # Exact formula: 0.45*80 + 0.40*80 + 0.15*(100-10) = 36 + 32 + 13.5 = 81.5
    assert compute_overall(80, 80, 10) == 81.5


def test_compute_overall_clamps_to_100():
    assert compute_overall(100, 100, 0) <= 100.0


def _seed_raw_trends() -> list[int]:
    ids = []
    with session_scope() as session:
        for i in range(3):
            r = RawTrend(
                source=Source.youtube,
                title=f"AI Bigfoot vlog part {i}",
                metrics_json={"views": 1000 * (i + 1)},
            )
            session.add(r)
            session.flush()
            ids.append(r.id)
    return ids


def _classifier_with_response(result: ClassificationResult) -> TrendClassifier:
    clf = TrendClassifier.__new__(TrendClassifier)  # bypass __init__/API key
    clf.client = MagicMock()
    clf.model = "claude-sonnet-4-6"
    parsed = MagicMock()
    parsed.parsed_output = result
    clf.client.messages.parse.return_value = parsed
    return clf


def test_run_inserts_new_trend():
    raw_ids = _seed_raw_trends()
    result = ClassificationResult(
        trends=[
            ClassifiedTrend(
                name="Bigfoot vlog",
                summary="Bigfoot films his daily life.",
                category="creature-vlog",
                is_ai_trend=True,
                momentum_score=85,
                saturation_score=20,
                fit_score=90,
                raw_trend_ids=raw_ids,
            )
        ]
    )
    clf = _classifier_with_response(result)
    summary = clf.run()

    assert summary["raw_processed"] == 3
    assert summary["trends_new"] == 1

    with session_scope() as session:
        trend = session.query(Trend).filter_by(name="Bigfoot vlog").one()
        assert trend.is_ai_trend is True
        assert trend.status == TrendStatus.new
        assert sorted(trend.raw_trend_ids) == sorted(raw_ids)
        # 0.45*85 + 0.40*90 + 0.15*(100-20) = 38.25 + 36 + 12 = 86.25
        assert trend.overall_score == 86.25


def test_run_merges_into_existing_trend():
    raw_ids = _seed_raw_trends()

    with session_scope() as session:
        session.add(
            Trend(
                name="Bigfoot vlog",
                raw_trend_ids=[raw_ids[0]],
                is_ai_trend=True,
                status=TrendStatus.new,
            )
        )

    result = ClassificationResult(
        trends=[
            ClassifiedTrend(
                name="Bigfoot vlog",
                summary="updated",
                category="creature-vlog",
                is_ai_trend=True,
                momentum_score=50,
                saturation_score=50,
                fit_score=50,
                raw_trend_ids=raw_ids[1:],
            )
        ]
    )
    clf = _classifier_with_response(result)
    summary = clf.run()

    assert summary["trends_new"] == 0
    assert summary["trends_updated"] == 1

    with session_scope() as session:
        trend = session.query(Trend).filter_by(name="Bigfoot vlog").one()
        # Evidence merged, deduplicated
        assert sorted(trend.raw_trend_ids) == sorted(raw_ids)
        assert trend.summary == "updated"


def test_run_skips_already_classified():
    raw_ids = _seed_raw_trends()
    with session_scope() as session:
        session.add(Trend(name="Existing", raw_trend_ids=raw_ids, status=TrendStatus.new))

    clf = _classifier_with_response(ClassificationResult(trends=[]))
    summary = clf.run()
    # All raw trends already linked -> nothing to process, no API call
    assert summary["raw_processed"] == 0
    clf.client.messages.parse.assert_not_called()
