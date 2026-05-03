"""Add profiles.metadata_json column + seed default config for venura_data_analyst.

Idempotent — safe to re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from db.database import get_engine, get_session
from db.models import Profile

DEFAULT_PROFILE_META = {
    "allowed_locations": ["US", "Remote-US", "Remote-Global", "Unknown"],
    "english_only": True,
    "posted_after_days": 30,
    "hide_citizenship_required": True,
    "hide_license_required": True,
    "hide_ghost_jobs_above": 80,
    "home_metro": "sacramento",
    "home_region": "california",
    "geo_boost_local": 20,
    "geo_boost_regional": 10,
    "geo_boost_domestic": 0,
}


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(profiles)")).fetchall()
        col_names = {row[1] for row in cols}
        if "metadata_json" in col_names:
            print("profiles.metadata_json already exists.")
        else:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN metadata_json TEXT"))
            print("Added profiles.metadata_json.")

    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.name == "venura_data_analyst")
        ).scalar_one_or_none()
        if profile is None:
            print("Profile venura_data_analyst not found; skipping default config seed.")
            return
        if profile.metadata_json:
            print(
                f"venura_data_analyst.metadata_json already set: {profile.metadata_json}"
            )
            return
        profile.metadata_json = DEFAULT_PROFILE_META
        session.commit()
        print(f"Seeded venura_data_analyst.metadata_json = {DEFAULT_PROFILE_META}")


if __name__ == "__main__":
    main()
