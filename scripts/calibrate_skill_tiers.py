"""Set criteria.weight_tier on the venura_data_analyst profile.

Phase 4.6b.1 fix — the original tier lists used multi-word phrases
("it support", "linux cli") that don't exist in the actual criteria
table (resume-extracted tokens are single words). The remapped lists
below match the user's real criterion terms (data tooling and
programming languages from a CS-grad pivoting toward data work) so
the skill_density_bonus actually fires instead of every item ending
up at the -30% floor.

Strategy:
  Tier 1 (3 points) — deepest hands-on tooling for the project the
    user actually built (Streamlit + pandas + Python). These match
    nearly every data-analyst JD and validate real fit.
  Tier 2 (2 points, also the default) — real and adjacent ecosystem.
    Falling here means "no change" from the migration default.
  Tier 3 (1 point) — present in the resume / criteria but generic
    or shallow signal. Includes the role keyword and unrelated
    languages from a CS-grad's general toolset.

Skipped: kind=exclude rows (anti-keywords like "senior" / "principal").
These never represent skills the user has and shouldn't contribute to
skill density at all; dashboard/data.py filters them out before
passing the criteria list to compute_land_score.

Idempotent. Run after migrate_add_weight_tier.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter

from sqlalchemy import select

from db.database import get_session
from db.models import Criterion, Profile

PROFILE_NAME = "venura_data_analyst"

# Single-token forms — the actual shape of criteria in the DB.
TIER_1_SKILLS: set[str] = {
    "python",
    "sql",
    "excel",
    "git",
    "github",
    "pandas",
    "jupyter",
}

TIER_2_SKILLS: set[str] = {
    "analytics",
    "numpy",
    "plotly",
    "streamlit",
    "sqlite",
    "eda",
}

TIER_3_SKILLS: set[str] = {
    "mongodb",
    "c++",
    "java",
    "javascript",
    "anomaly detection",
    "data analyst",
}


def _classify(term: str) -> int:
    t = (term or "").lower().strip()
    if t in TIER_1_SKILLS:
        return 1
    if t in TIER_2_SKILLS:
        return 2
    if t in TIER_3_SKILLS:
        return 3
    return 2  # default — falls through to "real" tier


def main() -> None:
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.name == PROFILE_NAME)
        ).scalar_one_or_none()
        if profile is None:
            print(f"Profile {PROFILE_NAME!r} not found.")
            return

        criteria = session.execute(
            select(Criterion).where(Criterion.profile_id == profile.id)
        ).scalars().all()

        before = Counter(c.weight_tier for c in criteria)
        changed = 0
        for c in criteria:
            tier = _classify(c.term)
            if c.weight_tier != tier:
                c.weight_tier = tier
                changed += 1
        session.commit()
        after = Counter(c.weight_tier for c in criteria)

    def _fmt(counter: Counter) -> str:
        return ", ".join(
            f"tier{tier}={counter.get(tier, 0)}" for tier in (1, 2, 3)
        )

    print(f"Calibrated {changed} of {len(criteria)} criterion rows.")
    print(f"  Before: {_fmt(before)}")
    print(f"  After:  {_fmt(after)}")


if __name__ == "__main__":
    main()
