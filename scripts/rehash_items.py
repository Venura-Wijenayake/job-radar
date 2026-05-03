"""One-shot migration: recompute every item's content_hash with the
normalized algorithm and collapse duplicate clusters.

Strategy:
  1. Recompute hash for each Item using ``_normalized_content_hash``.
  2. Group by new hash; any group with > 1 item is a duplicate cluster.
  3. Within each cluster keep the row with the smallest id (oldest);
     delete the rest along with their dependent rows in scores,
     tracking, keyword_extracts, and applications.

Idempotent: re-running on an already-deduped DB produces 0 new
clusters and removes nothing.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select

from db.database import get_session
from db.models import (
    Application,
    Item,
    KeywordExtract,
    Score,
    Tracking,
)
from scrapers.base import _normalized_content_hash


def main() -> None:
    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()
        items_before = len(items)

        # Pass 1 — recompute hashes
        hash_to_ids: dict[str, list[int]] = defaultdict(list)
        for item in items:
            company = (item.metadata_json or {}).get("company")
            new_hash = _normalized_content_hash(
                item.title or "", company, item.body or ""
            )
            item.content_hash = new_hash
            hash_to_ids[new_hash].append(item.id)
        session.commit()

        print(f"Rehashed {items_before} items.")

        # Pass 2 — find clusters and collect ids to delete
        clusters = {h: ids for h, ids in hash_to_ids.items() if len(ids) > 1}
        ids_to_delete: list[int] = []
        for ids in clusters.values():
            sorted_ids = sorted(ids)
            ids_to_delete.extend(sorted_ids[1:])  # keep smallest, delete the rest

        print(f"Found {len(clusters)} new duplicate cluster(s).")

        if not ids_to_delete:
            print(f"Items before: {items_before}, after: {items_before}, removed: 0")
            return

        # Pass 3 — delete dependent rows then the items themselves
        session.execute(delete(Score).where(Score.item_id.in_(ids_to_delete)))
        session.execute(delete(Tracking).where(Tracking.item_id.in_(ids_to_delete)))
        session.execute(
            delete(KeywordExtract).where(KeywordExtract.item_id.in_(ids_to_delete))
        )
        session.execute(
            delete(Application).where(Application.item_id.in_(ids_to_delete))
        )
        session.execute(delete(Item).where(Item.id.in_(ids_to_delete)))
        session.commit()

        items_after = items_before - len(ids_to_delete)
        print(
            f"Items before: {items_before}, after: {items_after}, "
            f"removed: {len(ids_to_delete)}"
        )


if __name__ == "__main__":
    main()
