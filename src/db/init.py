"""Create the SQLite database and all tables.

Idempotent — safe to run repeatedly. Run:
    python -m db.init
"""

from __future__ import annotations

from pathlib import Path

from config import get_settings
from db.models import Base
from db.session import get_engine


def init_db() -> None:
    settings = get_settings()
    url = settings.DATABASE_URL

    # Ensure the parent directory exists for file-based SQLite DBs.
    if url.startswith("sqlite:///"):
        db_path = Path(url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    Base.metadata.create_all(engine)
    return None


if __name__ == "__main__":
    init_db()
    settings = get_settings()
    print("Database initialised successfully.")
    print(f"  URL:    {settings.DATABASE_URL}")
    print("  Tables: raw_trends, trends, pipeline_logs")
