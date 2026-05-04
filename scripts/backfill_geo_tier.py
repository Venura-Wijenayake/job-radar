"""Backfill geo_tier on existing items using the current classifier.

Iterates every Item, runs classify_geo_tier on the raw location
signal (or first_line / region for sources without a top-level
location), persists the result to metadata_json.geo_tier.

Idempotent. Prints a tier-distribution summary at the end.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Item
from scoring.location_utils import classify_geo_tier


def main() -> None:
    updated = 0
    counts: Counter[str] = Counter()

    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()
        for item in items:
            md = dict(item.metadata_json or {})
            raw_loc = (
                md.get("location")
                or md.get("region")
                or md.get("first_line")
            )
            tier = classify_geo_tier(raw_loc, item.body)
            md["geo_tier"] = tier
            item.metadata_json = md
            counts[tier] += 1
            updated += 1
        session.commit()

    print(f"Backfilled {updated} items.")
    print("Geo-tier distribution:")
    for tier in ("local", "regional", "domestic", "unknown", "foreign"):
        print(f"  {tier:<10} {counts.get(tier, 0)}")


if __name__ == "__main__":
    main()
