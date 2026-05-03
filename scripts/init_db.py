"""Create the SQLite schema and seed default sources."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db
from db.seed import seed_sources


def main() -> None:
    init_db()
    inserted = seed_sources()
    print(f"Database initialized. Seeded {inserted} new source(s).")


if __name__ == "__main__":
    main()
