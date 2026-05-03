"""Seed exclude-kind criteria (anti-keywords) for a profile.

Idempotent: re-running adds only the missing rows. Used to penalize
seniority-oriented listings against an entry-level profile.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Criterion, Profile

ANTI_KEYWORDS: list[str] = [
    "senior",
    "principal",
    "staff",
    "lead",
    "director",
    "manager",
    "head of",
    "vp",
    "chief",
    "vice president",
    "sr.",
]

# Anti-keywords whose match should hurt more than the default. Phase 3.7
# upgraded these from -20 to -30 (weight 2 -> 3) because Product/Project
# Manager and Director-level roles were still surfacing despite the
# generic anti-keyword penalty.
HIGH_PENALTY_TERMS: set[str] = {
    "manager", "head of", "director", "vp", "chief"
}


def _desired_weight(term: str) -> int:
    return 3 if term in HIGH_PENALTY_TERMS else 2


def seed_antikeywords(profile_name: str) -> dict[str, int]:
    """Idempotently upsert ANTI_KEYWORDS as kind="exclude" criteria.

    Returns ``{"added": int, "updated": int, "unchanged": int}`` —
    ``updated`` counts rows whose stored weight diverged from the
    desired weight (e.g. after a HIGH_PENALTY_TERMS bump). Raises
    ``ValueError`` if the profile name does not exist.
    """
    added = 0
    updated = 0
    unchanged = 0
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.name == profile_name)
        ).scalar_one_or_none()
        if profile is None:
            raise ValueError(f"Profile not found: {profile_name!r}")

        for term in ANTI_KEYWORDS:
            desired = _desired_weight(term)
            existing = session.execute(
                select(Criterion).where(
                    Criterion.profile_id == profile.id,
                    Criterion.term == term,
                    Criterion.kind == "exclude",
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Criterion(
                        profile_id=profile.id,
                        term=term,
                        kind="exclude",
                        weight=desired,
                        match_type="fuzzy",
                        source="manual",
                    )
                )
                added += 1
            elif existing.weight != desired:
                existing.weight = desired
                updated += 1
            else:
                unchanged += 1

        session.commit()

    return {"added": added, "updated": updated, "unchanged": unchanged}


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/seed_antikeywords.py <profile_name>",
            file=sys.stderr,
        )
        sys.exit(2)
    profile_name = sys.argv[1]
    try:
        summary = seed_antikeywords(profile_name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(
        f"Added {summary['added']}, updated {summary['updated']}, "
        f"unchanged {summary['unchanged']}."
    )


if __name__ == "__main__":
    main()
