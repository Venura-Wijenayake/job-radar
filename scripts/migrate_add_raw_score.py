"""One-shot migration: add scores.raw_score (REAL, nullable) if missing.

Idempotent — safe to re-run. Replaces the need for Alembic for a single
column addition. New databases initialized via init_db() get the column
automatically from the model.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from db.database import get_engine


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(scores)")).fetchall()
        col_names = {row[1] for row in cols}
        if "raw_score" in col_names:
            print("scores.raw_score already exists — nothing to do.")
            return
        conn.execute(text("ALTER TABLE scores ADD COLUMN raw_score REAL"))
    print("Added scores.raw_score.")


if __name__ == "__main__":
    main()
