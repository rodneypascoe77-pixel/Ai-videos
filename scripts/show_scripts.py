"""Print the selected scripts for the top trend. Read-only inspection.

    uv run python scripts/show_scripts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from db.models import Script, ScriptStatus, Trend
from db.session import session_scope


def _ascii(text: str) -> str:
    return (text or "").encode("ascii", "replace").decode("ascii")


def main() -> None:
    with session_scope() as session:
        trend = (
            session.query(Trend)
            .filter(Trend.is_ai_trend.is_(True))
            .order_by(Trend.overall_score.desc())
            .first()
        )
        if trend is None:
            print("No AI trends found.")
            return

        print(f"TREND: {_ascii(trend.name)}  (overall {trend.overall_score})")
        print(f"  {_ascii(trend.summary or '')}\n")

        selected = (
            session.query(Script)
            .filter(Script.trend_id == trend.id, Script.status == ScriptStatus.selected)
            .order_by(Script.selection_rank)
            .all()
        )
        for s in selected:
            print("=" * 72)
            print(f"#{s.selection_rank}  (quality {s.quality_score})  {_ascii(s.title)}")
            print(f"Premise: {_ascii(s.premise or '')}")
            print(f"Why picked: {_ascii(s.selection_reasoning or '')}")
            print("-" * 72)
            print(_ascii(s.script_text))
            print()


if __name__ == "__main__":
    main()
