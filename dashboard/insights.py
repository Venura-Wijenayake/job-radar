"""Pure chart-data helpers for the Market Insights tab.

Each function returns a ``list[dict]`` so the calling Streamlit code
can convert to a Plotly-friendly DataFrame at the render site. No
Plotly imports here — keeps these unit-testable without the chart
runtime.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlalchemy import func, select

from db.database import get_session
from db.models import Item, KeywordExtract, Source


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def top_hiring_companies(limit: int = 15) -> list[dict]:
    """Companies posting the most items. Excludes "Unknown" / null names."""
    counts: Counter[str] = Counter()
    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()
    for item in items:
        company = (item.metadata_json or {}).get("company")
        if not company or company == "Unknown":
            continue
        counts[company] += 1
    return [{"company": c, "count": n} for c, n in counts.most_common(limit)]


def skill_demand_frequency(
    taxonomy_path: Path | str, top_n: int = 20
) -> list[dict]:
    """For each taxonomy skill term, how many items mention it.

    Backed by the cached keyword_extracts table — fast even on the full
    corpus. Multi-word taxonomy terms ("a/b testing", "power bi") won't
    match here because the tokenizer splits on spaces; that's a known
    limitation accepted for the MVP.
    """
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        tax = yaml.safe_load(f) or {}

    skill_terms: set[str] = set()
    for category in (tax.get("skills") or {}).values():
        for term in category:
            skill_terms.add(term.lower())

    counts: Counter[str] = Counter()
    with get_session() as session:
        extracts = session.execute(select(KeywordExtract)).scalars().all()
    for ext in extracts:
        kws = ext.keywords_json or []
        seen_in_this_item: set[str] = set()
        for kw in kws:
            term = (kw.get("term") or "").lower()
            if term in skill_terms and term not in seen_in_this_item:
                counts[term] += 1
                seen_in_this_item.add(term)

    return [{"skill": s, "item_count": n} for s, n in counts.most_common(top_n)]


def posting_velocity_by_day(days: int = 30) -> list[dict]:
    """Item count per day over the last ``days`` days. Skips items with
    NULL ``posted_at``."""
    cutoff = _now_utc_naive() - timedelta(days=days)
    with get_session() as session:
        items = session.execute(
            select(Item).where(Item.posted_at >= cutoff)
        ).scalars().all()

    by_day: defaultdict[str, int] = defaultdict(int)
    for item in items:
        if item.posted_at is None:
            continue
        day = item.posted_at.strftime("%Y-%m-%d")
        by_day[day] += 1

    return [{"date": d, "count": c} for d, c in sorted(by_day.items())]


def source_breakdown() -> list[dict]:
    """Item count per source with percentage of total."""
    with get_session() as session:
        rows = session.execute(
            select(Source.name, func.count(Item.id))
            .join(Item, Item.source_id == Source.id)
            .group_by(Source.id, Source.name)
        ).all()

    total = sum(count for _, count in rows)
    if total == 0:
        return []

    breakdown = [
        {
            "source_name": name,
            "count": count,
            "percentage": round((count / total) * 100, 1),
        }
        for name, count in rows
    ]
    breakdown.sort(key=lambda r: r["count"], reverse=True)
    return breakdown


def market_summary() -> dict:
    """Headline metrics for the top of the Insights tab."""
    with get_session() as session:
        total_items = session.execute(select(func.count(Item.id))).scalar_one()
        freshest = session.execute(
            select(func.max(Item.posted_at))
        ).scalar_one()
        items = session.execute(select(Item)).scalars().all()
    companies = {
        (i.metadata_json or {}).get("company")
        for i in items
        if (i.metadata_json or {}).get("company")
        and (i.metadata_json or {}).get("company") != "Unknown"
    }
    return {
        "total_items": total_items,
        "total_companies": len(companies),
        "freshest_posted_at": freshest,
    }
