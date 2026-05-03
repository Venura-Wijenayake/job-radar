"""Parse a resume file and populate the corresponding profile + criteria."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Criterion
from scoring.resume_parser import parse_resume


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: python scripts/parse_resume.py <file_path> <profile_name>",
            file=sys.stderr,
        )
        sys.exit(2)

    file_path = sys.argv[1]
    profile_name = sys.argv[2]

    profile = parse_resume(file_path, profile_name)

    with get_session() as session:
        criteria = session.execute(
            select(Criterion).where(Criterion.profile_id == profile.id)
        ).scalars().all()

    by_kind = Counter(c.kind for c in criteria)

    print(f"Profile: {profile.name} (id={profile.id})")
    print(f"Resume:  {profile.resume_filename}")
    print(f"Parsed:  {profile.parsed_at}")
    print(f"Criteria extracted: {len(criteria)}")
    for kind, n in sorted(by_kind.items()):
        print(f"  {kind:8s} {n}")


if __name__ == "__main__":
    main()
