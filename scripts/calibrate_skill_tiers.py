"""Set criteria.weight_tier on the venura_data_analyst profile.

Phase 4.6b — assigns tier 1 / 2 / 3 to existing resume-derived
criteria using a hardcoded mapping sourced from the user's actual
resume content (Dell hardware tech experience, ITIL cert, Linux
Essentials, Python automation, basic SQL/Excel). Criteria not in
any tier list keep the default tier 2.

Idempotent — re-running with the same mapping is a no-op for already-
calibrated rows. Run after migrate_add_weight_tier.py.
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

TIER_1_SKILLS: set[str] = {
    "it support",
    "hardware diagnostics",
    "windows",
    "active directory",
    "ticketing",
    "itil",
    "linux cli",
    "linux",
    "troubleshooting",
    "incident response",
    "service desk",
    "help desk",
    "office 365",
    "microsoft office",
}

TIER_2_SKILLS: set[str] = {
    "python",
    "sql",
    "excel",
    "git",
    "github",
    "command line",
    "automation",
    "documentation",
}

TIER_3_SKILLS: set[str] = {
    "data validation",
    "scripting",
    "shell",
    "bash",
    "powershell",
    "data cleaning",
}


def _classify(term: str) -> int:
    t = (term or "").lower().strip()
    if t in TIER_1_SKILLS:
        return 1
    if t in TIER_2_SKILLS:
        return 2
    if t in TIER_3_SKILLS:
        return 3
    return 2  # default


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
