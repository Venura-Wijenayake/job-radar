"""Tests for dashboard.insights chart-data helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dashboard.insights import (
    market_summary,
    posting_velocity_by_day,
    skill_demand_frequency,
    source_breakdown,
    top_hiring_companies,
)
from db.database import get_session
from db.models import Item, KeywordExtract, Source

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "config" / "skills_taxonomy.yaml"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _add_source(name: str) -> int:
    with get_session() as session:
        s = Source(name=name, type="api", url=f"http://{name}", enabled=True)
        session.add(s)
        session.commit()
        return s.id


def _add_item(
    source_id: int,
    ext_id: str,
    title: str = "T",
    company: str | None = None,
    posted_at: datetime | None = None,
) -> int:
    with get_session() as session:
        meta = {"company": company} if company else {}
        item = Item(
            source_id=source_id,
            external_id=ext_id,
            title=title,
            body="",
            url=f"http://t/{ext_id}",
            content_hash=f"h-{ext_id}",
            scraped_at=_now(),
            posted_at=posted_at,
            metadata_json=meta,
        )
        session.add(item)
        session.commit()
        return item.id


def _add_keyword_extract(item_id: int, keywords: list[dict]) -> None:
    with get_session() as session:
        session.add(
            KeywordExtract(
                item_id=item_id,
                keywords_json=keywords,
                extracted_at=_now(),
            )
        )
        session.commit()


def test_top_hiring_companies_excludes_unknown_and_null(fresh_db):
    sid = _add_source("Test")
    _add_item(sid, "1", company="Acme")
    _add_item(sid, "2", company="Acme")
    _add_item(sid, "3", company="Unknown")
    _add_item(sid, "4", company=None)
    _add_item(sid, "5", company="Beta")

    result = top_hiring_companies(10)
    companies = {r["company"]: r["count"] for r in result}
    assert "Acme" in companies
    assert "Beta" in companies
    assert "Unknown" not in companies
    assert None not in companies


def test_top_hiring_companies_sorts_descending(fresh_db):
    sid = _add_source("Test")
    for i in range(3):
        _add_item(sid, f"a-{i}", company="Acme")
    for i in range(5):
        _add_item(sid, f"b-{i}", company="Beta")
    for i in range(1):
        _add_item(sid, f"g-{i}", company="Gamma")

    result = top_hiring_companies(10)
    assert [r["company"] for r in result] == ["Beta", "Acme", "Gamma"]
    assert [r["count"] for r in result] == [5, 3, 1]


def test_skill_demand_counts_by_keyword_extracts(fresh_db):
    sid = _add_source("Test")
    a = _add_item(sid, "a")
    b = _add_item(sid, "b")
    c = _add_item(sid, "c")
    # python in items a + b; sql in c only
    _add_keyword_extract(a, [{"term": "python", "frequency": 5, "importance": 2.0}])
    _add_keyword_extract(b, [{"term": "python", "frequency": 1, "importance": 2.0}])
    _add_keyword_extract(c, [{"term": "sql", "frequency": 3, "importance": 2.0}])

    result = skill_demand_frequency(TAXONOMY_PATH, top_n=20)
    counts = {r["skill"]: r["item_count"] for r in result}
    # python is in 2 items, sql in 1 — counts items, not occurrences
    assert counts.get("python") == 2
    assert counts.get("sql") == 1


def test_posting_velocity_groups_by_day(fresh_db):
    sid = _add_source("Test")
    today = _now()
    yesterday = today - timedelta(days=1)
    _add_item(sid, "a", posted_at=today)
    _add_item(sid, "b", posted_at=today)
    _add_item(sid, "c", posted_at=yesterday)

    result = posting_velocity_by_day(7)
    by_day = {r["date"]: r["count"] for r in result}
    assert by_day[today.strftime("%Y-%m-%d")] == 2
    assert by_day[yesterday.strftime("%Y-%m-%d")] == 1


def test_posting_velocity_filters_by_days_param(fresh_db):
    sid = _add_source("Test")
    recent = _now() - timedelta(days=2)
    old = _now() - timedelta(days=20)
    _add_item(sid, "a", posted_at=recent)
    _add_item(sid, "b", posted_at=old)

    seven_days = posting_velocity_by_day(7)
    thirty_days = posting_velocity_by_day(30)

    seven_total = sum(r["count"] for r in seven_days)
    thirty_total = sum(r["count"] for r in thirty_days)
    assert seven_total == 1
    assert thirty_total == 2


def test_source_breakdown_percentages_sum_to_100(fresh_db):
    sid_a = _add_source("SourceA")
    sid_b = _add_source("SourceB")
    sid_c = _add_source("SourceC")
    for i in range(7):
        _add_item(sid_a, f"a-{i}")
    for i in range(2):
        _add_item(sid_b, f"b-{i}")
    _add_item(sid_c, "c-1")

    result = source_breakdown()
    total_pct = sum(r["percentage"] for r in result)
    # Allow tiny rounding drift.
    assert abs(total_pct - 100.0) < 0.5
    assert [r["source_name"] for r in result] == ["SourceA", "SourceB", "SourceC"]


def test_market_summary_returns_expected_keys(fresh_db):
    sid = _add_source("Test")
    _add_item(sid, "a", company="Acme", posted_at=_now())
    _add_item(sid, "b", company="Beta", posted_at=_now())

    summary = market_summary()
    assert summary["total_items"] == 2
    assert summary["total_companies"] == 2
    assert summary["freshest_posted_at"] is not None
