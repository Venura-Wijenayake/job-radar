"""Score every item in the DB against a named profile."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import desc, select

from db.database import get_session
from db.models import Item, Profile, Score, Source
from scoring.batch import score_all_items


def _format_distribution(dist: dict) -> str:
    keys = ["0-25", "25-50", "50-75", "75-100"]
    return " | ".join(f"{k}: {dist[k]:>3}" for k in keys)


def _print_top(profile_id: int, n: int = 10) -> None:
    with get_session() as session:
        rows = session.execute(
            select(Score, Item, Source)
            .join(Item, Score.item_id == Item.id)
            .join(Source, Item.source_id == Source.id)
            .where(Score.profile_id == profile_id)
            .order_by(desc(Score.score), desc(Score.computed_at))
            .limit(n)
        ).all()

    print(f"\n=== Top {n} ===")
    for i, (score_row, item, _source) in enumerate(rows, 1):
        company = (item.metadata_json or {}).get("company") or "?"
        terms = sorted(
            score_row.matched_terms_json or [],
            key=lambda t: t["contribution"],
            reverse=True,
        )[:3]
        terms_str = ", ".join(
            f"{t['term']}({t['contribution']:.0f}{'*' if t.get('in_title') else ''})"
            for t in terms
        ) or "—"
        title = (item.title or "")[:50]
        company = company[:22]
        raw = score_row.raw_score if score_row.raw_score is not None else 0.0
        print(
            f"  {i:2d}. [{score_row.score:5.1f}] (raw {raw:6.1f})  "
            f"{title:<50}  @ {company:<22}  {terms_str}"
        )


def _print_bottom(profile_id: int, n: int = 3) -> None:
    with get_session() as session:
        rows = session.execute(
            select(Score, Item, Source)
            .join(Item, Score.item_id == Item.id)
            .join(Source, Item.source_id == Source.id)
            .where(Score.profile_id == profile_id)
            .order_by(Score.score, Score.computed_at)
            .limit(n)
        ).all()

    print(f"\n=== Bottom {n} ===")
    for i, (score_row, item, _source) in enumerate(rows, 1):
        company = (item.metadata_json or {}).get("company") or "?"
        title = (item.title or "")[:55]
        company = company[:22]
        print(f"  {i:2d}. [{score_row.score:5.1f}]  {title:<55}  @ {company:<22}")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/score_items.py <profile_name> [--force]",
            file=sys.stderr,
        )
        sys.exit(2)

    profile_name = sys.argv[1]
    force = "--force" in sys.argv[2:]

    summary = score_all_items(profile_name, force=force)

    print("=== Scoring summary ===")
    print(f"Profile:       {profile_name}")
    print(f"Total items:   {summary['total_items']}")
    print(f"Scored:        {summary['scored']}")
    print(f"Skipped:       {summary['skipped']}")
    print(f"Errors:        {summary['errors']}")
    print(f"Distribution:  {_format_distribution(summary['score_distribution'])}")

    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.name == profile_name)
        ).scalar_one()
        profile_id = profile.id

    _print_top(profile_id, n=10)
    _print_bottom(profile_id, n=3)


if __name__ == "__main__":
    main()
