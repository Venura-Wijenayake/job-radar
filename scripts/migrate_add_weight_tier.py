"""Add criteria.weight_tier (INTEGER, default 2) if missing.

Phase 4.6b — supports the land_score skill-density bonus by tagging
each criterion as tier 1 (strongest), 2 (real), or 3 (mentioned).
Idempotent — safe to re-run.
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
        cols = conn.execute(text("PRAGMA table_info(criteria)")).fetchall()
        col_names = {row[1] for row in cols}
        if "weight_tier" in col_names:
            print("criteria.weight_tier already exists - nothing to do.")
            return
        conn.execute(
            text(
                "ALTER TABLE criteria ADD COLUMN weight_tier "
                "INTEGER NOT NULL DEFAULT 2"
            )
        )
    print("Added criteria.weight_tier (default 2).")


if __name__ == "__main__":
    main()
