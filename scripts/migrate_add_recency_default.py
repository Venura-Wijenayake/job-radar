"""Backfill the posted_after_days field on existing profiles.metadata_json.

Profiles created before Phase 3.7 don't have ``posted_after_days`` in
their metadata; this migration adds the default (30) to any profile
that's missing it. Idempotent — runs that find nothing to do report 0
updates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Profile

DEFAULT_DAYS = 30


def main() -> None:
    updated = 0
    unchanged = 0

    with get_session() as session:
        profiles = session.execute(select(Profile)).scalars().all()
        for profile in profiles:
            md = dict(profile.metadata_json or {})
            if "posted_after_days" in md:
                unchanged += 1
                continue
            md["posted_after_days"] = DEFAULT_DAYS
            profile.metadata_json = md
            updated += 1
        session.commit()

    print(f"Updated {updated} profile(s), {unchanged} unchanged.")


if __name__ == "__main__":
    main()
