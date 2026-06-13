"""Tests for Phase 2 script generation/selection (Anthropic client mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from db.models import Script, ScriptStatus, Trend, TrendStatus
from db.session import session_scope
from generation.generator import ScriptGenerator
from generation.schema import (
    GeneratedScript,
    ScriptBatch,
    ScriptSelection,
    SelectionResult,
)
from generation.selector import ScriptSelector


def _make_trend(status=TrendStatus.new, is_ai=True, score=90.0) -> int:
    with session_scope() as session:
        t = Trend(
            name="Bigfoot vlog",
            summary="Bigfoot films his day.",
            category="creature-vlog",
            is_ai_trend=is_ai,
            overall_score=score,
            status=status,
        )
        session.add(t)
        session.flush()
        return t.id


def _generator_returning(batch: ScriptBatch) -> ScriptGenerator:
    gen = ScriptGenerator.__new__(ScriptGenerator)
    gen.client = MagicMock()
    gen.model = "claude-sonnet-4-6"
    parsed = MagicMock()
    parsed.parsed_output = batch
    gen.client.messages.parse.return_value = parsed
    return gen


def _selector_returning(result: SelectionResult) -> ScriptSelector:
    sel = ScriptSelector.__new__(ScriptSelector)
    sel.client = MagicMock()
    sel.model = "claude-sonnet-4-6"
    parsed = MagicMock()
    parsed.parsed_output = result
    sel.client.messages.parse.return_value = parsed
    return sel


def _batch(n: int, prefix="S") -> ScriptBatch:
    return ScriptBatch(
        scripts=[
            GeneratedScript(title=f"{prefix}{i}", premise=f"premise {i}", script_text=f"script {i}")
            for i in range(n)
        ]
    )


def test_generate_persists_target_scripts():
    trend_id = _make_trend()
    gen = _generator_returning(_batch(5))  # every batch returns 5

    ids = gen.generate(trend_id, target=10)

    assert len(ids) == 10  # two batches of 5
    with session_scope() as session:
        rows = session.query(Script).filter_by(trend_id=trend_id).all()
        assert len(rows) == 10
        assert all(r.status == ScriptStatus.generated for r in rows)


def test_generate_unknown_trend_raises():
    gen = _generator_returning(_batch(5))
    try:
        gen.generate(99999, target=5)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_select_marks_top_keep_and_rejects_rest():
    trend_id = _make_trend()
    # Seed 4 generated scripts
    with session_scope() as session:
        for i in range(4):
            session.add(
                Script(
                    trend_id=trend_id,
                    title=f"S{i}",
                    script_text=f"text {i}",
                    status=ScriptStatus.generated,
                )
            )

    # Model scores index 2 highest, then 0, then 3, then 1
    result = SelectionResult(
        selected=[
            ScriptSelection(index=2, quality_score=95, reasoning="best"),
            ScriptSelection(index=0, quality_score=88, reasoning="good"),
            ScriptSelection(index=3, quality_score=70, reasoning="ok"),
            ScriptSelection(index=1, quality_score=40, reasoning="weak"),
        ]
    )
    sel = _selector_returning(result)
    selected_ids = sel.select(trend_id, keep=2)

    assert len(selected_ids) == 2
    with session_scope() as session:
        rows = {r.title: r for r in session.query(Script).filter_by(trend_id=trend_id).all()}
        assert rows["S2"].status == ScriptStatus.selected
        assert rows["S2"].selection_rank == 1
        assert rows["S0"].status == ScriptStatus.selected
        assert rows["S0"].selection_rank == 2
        assert rows["S3"].status == ScriptStatus.rejected
        assert rows["S1"].status == ScriptStatus.rejected
        # Every scored script keeps its quality_score
        assert rows["S2"].quality_score == 95


def test_select_no_candidates_returns_empty():
    trend_id = _make_trend()
    sel = _selector_returning(SelectionResult(selected=[]))
    assert sel.select(trend_id) == []
    sel.client.messages.parse.assert_not_called()


def test_runner_processes_and_queues_trend(monkeypatch):
    import generation.runner as runner

    trend_id = _make_trend()

    gen = _generator_returning(_batch(5))
    sel_result = SelectionResult(
        selected=[ScriptSelection(index=i, quality_score=90 - i, reasoning="r") for i in range(5)]
    )
    sel = _selector_returning(sel_result)

    monkeypatch.setattr(runner, "init_db", lambda: None)
    monkeypatch.setattr(runner, "ScriptGenerator", lambda model=None: gen)
    monkeypatch.setattr(runner, "ScriptSelector", lambda model=None: sel)

    totals = runner.run(max_trends=5)

    assert totals["trends_processed"] == 1
    assert totals["scripts_generated"] == 25  # DEFAULT_TARGET (5 batches x 5)
    assert totals["scripts_selected"] == 3  # DEFAULT_KEEP

    with session_scope() as session:
        trend = session.get(Trend, trend_id)
        assert trend.status == TrendStatus.queued


def test_runner_skips_non_eligible_trends():
    import generation.runner as runner

    # queued + non-AI trends are NOT eligible
    _make_trend(status=TrendStatus.queued)
    _make_trend(status=TrendStatus.new, is_ai=False)

    assert runner.select_eligible_trend_ids(10) == []
