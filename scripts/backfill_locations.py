"""Backfill location_normalized + language_detected on existing items.

For every Item where the new metadata fields are missing, run them
through normalize_location() and detect_language() and persist the
result. Idempotent — items already annotated are skipped.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Item
from scoring.language_utils import detect_language
from scoring.location_utils import normalize_location


def main() -> None:
    backfilled = 0
    skipped = 0
    location_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()

    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()

        for item in items:
            md = dict(item.metadata_json or {})
            if "location_normalized" in md and "language_detected" in md:
                skipped += 1
                location_counts[md["location_normalized"]] += 1
                language_counts[md["language_detected"]] += 1
                continue

            raw_loc = md.get("location") or md.get("region") or md.get("first_line")
            md["location_normalized"] = normalize_location(raw_loc, item.body)
            md["language_detected"] = detect_language(item.body or "")
            item.metadata_json = md

            backfilled += 1
            location_counts[md["location_normalized"]] += 1
            language_counts[md["language_detected"]] += 1

        session.commit()

    print(f"Backfilled {backfilled} items, {skipped} skipped (already annotated).")
    print()
    print("Location distribution:")
    for loc, n in location_counts.most_common():
        print(f"  {loc:<16} {n}")
    print()
    print("Language distribution:")
    for lang, n in language_counts.most_common():
        print(f"  {lang:<10} {n}")


if __name__ == "__main__":
    main()
