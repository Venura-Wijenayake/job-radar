"""Add allowed_geo_tiers default to existing profiles.metadata_json.

Idempotent. Adds the Phase 4.2.1 key to any profile that doesn't already
have it. Defaults to ["local", "regional", "domestic", "unknown"] —
"foreign" is excluded so foreign-location postings drop out of the
daily queue at default settings.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Profile

DEFAULTS = {
    "allowed_geo_tiers": ["local", "regional", "domestic", "unknown"],
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
    print(f"Updated {updated} profile(s), {unchanged} already had the key.")


if __name__ == "__main__":
    main()
