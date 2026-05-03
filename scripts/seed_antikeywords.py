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


def seed_antikeywords(profile_name: str) -> dict[str, int]:
    """Idempotently insert ANTI_KEYWORDS as kind="exclude" criteria.

    Returns ``{"added": int, "skipped": int}``. Raises ``ValueError`` if
    the profile name does not exist.
    """
    added = 0
    skipped = 0
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.name == profile_name)
        ).scalar_one_or_none()
        if profile is None:
            raise ValueError(f"Profile not found: {profile_name!r}")

        for term in ANTI_KEYWORDS:
            existing = session.execute(
                select(Criterion).where(
                    Criterion.profile_id == profile.id,
                    Criterion.term == term,
                    Criterion.kind == "exclude",
                )
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                continue
            session.add(
                Criterion(
                    profile_id=profile.id,
                    term=term,
                    kind="exclude",
                    weight=2,
                    match_type="fuzzy",
                    source="manual",
                )
            )
            added += 1

        session.commit()

    return {"added": added, "skipped": skipped}


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
        f"Added {summary['added']} anti-keywords, "
        f"skipped {summary['skipped']} existing."
    )


if __name__ == "__main__":
    main()
