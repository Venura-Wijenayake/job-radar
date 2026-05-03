"""Backfill geo-preference keys on existing profiles.metadata_json.

Idempotent. Adds the five Phase 4.1 keys to any profile that doesn't
already have them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Profile

DEFAULTS = {
    "home_metro": "sacramento",
    "home_region": "california",
    "geo_boost_local": 20,
    "geo_boost_regional": 10,
    "geo_boost_domestic": 0,
}


def main() -> None:
    updated = 0
    unchanged = 0
    with get_session() as session:
        profiles = session.execute(select(Profile)).scalars().all()
        for profile in profiles:
            md = dict(profile.metadata_json or {})
            missing = [k for k in DEFAULTS if k not in md]
            if not missing:
                unchanged += 1
                continue
            for k in missing:
                md[k] = DEFAULTS[k]
            profile.metadata_json = md
            updated += 1
        session.commit()
    print(f"Updated {updated} profile(s), {unchanged} already had the keys.")


if __name__ == "__main__":
    main()
