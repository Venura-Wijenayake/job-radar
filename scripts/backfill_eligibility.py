"""Recompute citizenship_required / license_required / ghost_score for every
existing item using the current detectors.

Idempotent — safe to re-run after detector updates. Prints a summary
distribution at the end.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Item
from scoring.eligibility_utils import (
    detect_citizenship_required,
    detect_license_required,
)
from scoring.ghost_utils import (
    GHOST_HARD_THRESHOLD,
    GHOST_WARN_THRESHOLD,
    compute_ghost_score,
)


def _bucket(score: int) -> str:
    if score >= GHOST_HARD_THRESHOLD:
        return "hide (>=80)"
    if score >= GHOST_WARN_THRESHOLD:
        return "warn (50-79)"
    return "ok (<50)"


def main() -> None:
    backfilled = 0
    citizenship_count = 0
    license_count = 0
    ghost_buckets: Counter[str] = Counter()

    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()
        for item in items:
            md = dict(item.metadata_json or {})
            body = item.body or ""

            md["citizenship_required"] = detect_citizenship_required(body)
            md["license_required"] = detect_license_required(body)
            md["ghost_score"] = compute_ghost_score(
                {
                    "title": item.title,
                    "body": body,
                    "company": md.get("company"),
                    "posted_at": item.posted_at,
                    "salary_min": md.get("salary_min"),
                    "salary_max": md.get("salary_max"),
                }
            )

            if md["citizenship_required"]:
                citizenship_count += 1
            if md["license_required"]:
                license_count += 1
            ghost_buckets[_bucket(md["ghost_score"])] += 1

            item.metadata_json = md
            backfilled += 1
        session.commit()

    print(f"Backfilled {backfilled} items.")
    print(f"Citizenship-required:  {citizenship_count}")
    print(f"License-required:      {license_count}")
    print("Ghost-score distribution:")
    for bucket in ("hide (>=80)", "warn (50-79)", "ok (<50)"):
        print(f"  {bucket:<14} {ghost_buckets.get(bucket, 0)}")


if __name__ == "__main__":
    main()
