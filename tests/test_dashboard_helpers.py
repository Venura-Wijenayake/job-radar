"""Tests for dashboard.data helpers — pure SQLAlchemy, no Streamlit."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from dashboard.data import (
    get_pipeline,
    get_stats,
    get_today_queue,
    set_status,
    update_notes,
)
from db.database import get_session
from db.models import Item, Profile, Score, Source, Tracking, TrackingStatus


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def basic_setup(fresh_db):
    """Source + profile (with parsed_at). Caller adds items / scores / tracking."""
    with get_session() as session:
        src = Source(name="Test", type="api", url="http://t", enabled=True)
        session.add(src)
        session.flush()
        profile = Profile(name="p1", parsed_at=_now())
        session.add(profile)
        session.flush()
        ids = {"source_id": src.id, "profile_id": profile.id}
        session.commit()
    return ids


def _add_item(
    source_id: int,
    ext_id: str,
    title: str,
    body: str = "",
    company: str | None = None,
    posted_at: datetime | None = None,
) -> int:
    with get_session() as session:
        item = Item(
            source_id=source_id,
            external_id=ext_id,
            title=title,
            body=body,
            url=f"http://t/{ext_id}",
            content_hash=f"h-{ext_id}",
            scraped_at=_now(),
            posted_at=posted_at,
            metadata_json={"company": company} if company else {},
        )
        session.add(item)
        session.commit()
        return item.id


def _add_score(
    item_id: int,
    profile_id: int,
    score: float,
    raw_score: float | None = None,
    matched_terms: list[dict] | None = None,
) -> None:
    with get_session() as session:
        session.add(
            Score(
                item_id=item_id,
                profile_id=profile_id,
                score=score,
                raw_score=raw_score if raw_score is not None else score,
                matched_terms_json=matched_terms or [],
                computed_at=_now(),
            )
        )
        session.commit()


def _add_tracking(
    item_id: int,
    profile_id: int,
    status: str,
    notes: str | None = None,
    applied_at: datetime | None = None,
) -> None:
    with get_session() as session:
        session.add(
            Tracking(
                item_id=item_id,
                profile_id=profile_id,
                status=TrackingStatus(status),
                notes=notes,
                applied_at=applied_at,
                last_status_change_at=_now(),
            )
        )
        session.commit()


# ----- get_today_queue -----


def test_get_today_queue_orders_by_score_desc(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A")
    b = _add_item(sid, "b", "Item B")
    c = _add_item(sid, "c", "Item C")
    _add_score(a, pid, 30)
    _add_score(b, pid, 90)
    _add_score(c, pid, 60)

    result = get_today_queue("p1")
    assert [r["score"] for r in result] == [90, 60, 30]
    assert [r["title"] for r in result] == ["Item B", "Item C", "Item A"]


def test_get_today_queue_excludes_hidden_and_skipped(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    items = []
    for i in range(1, 5):
        iid = _add_item(sid, str(i), f"Item {i}")
        _add_score(iid, pid, i * 10)
        items.append(iid)
    _add_tracking(items[0], pid, "hidden")
    _add_tracking(items[1], pid, "skipped")

    result = get_today_queue("p1")
    item_ids = {r["item_id"] for r in result}
    assert items[0] not in item_ids
    assert items[1] not in item_ids
    assert items[2] in item_ids
    assert items[3] in item_ids


def test_collapse_duplicates_groups_by_title_company(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Lead Analytics Engineer", company="Monzo")
    b = _add_item(sid, "b", "Lead Analytics Engineer", company="Monzo")
    c = _add_item(sid, "c", "Data Analyst", company="Acme")
    _add_score(a, pid, 80)
    _add_score(b, pid, 70)
    _add_score(c, pid, 60)

    result = get_today_queue("p1")
    assert len(result) == 2

    monzo = next(r for r in result if r["company"] == "Monzo")
    assert monzo["item_id"] == a
    assert monzo["score"] == 80
    assert monzo["similar_count"] == 1
    assert monzo["similar_item_ids"] == [b]

    acme = next(r for r in result if r["company"] == "Acme")
    assert acme["similar_count"] == 0
    assert acme["similar_item_ids"] == []


def test_collapse_duplicates_keeps_highest_score(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Lead Engineer", company="Monzo")
    b = _add_item(sid, "b", "Lead Engineer", company="Monzo")
    _add_score(a, pid, 50)
    _add_score(b, pid, 80)

    result = get_today_queue("p1")
    assert len(result) == 1
    assert result[0]["item_id"] == b
    assert result[0]["score"] == 80
    assert result[0]["similar_count"] == 1
    assert result[0]["similar_item_ids"] == [a]


def test_collapse_duplicates_off_returns_all(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Lead Engineer", company="Monzo")
    b = _add_item(sid, "b", "Lead Engineer", company="Monzo")
    _add_score(a, pid, 80)
    _add_score(b, pid, 70)

    result = get_today_queue("p1", collapse_duplicates=False)
    assert len(result) == 2
    assert {r["item_id"] for r in result} == {a, b}


def test_collapse_handles_empty_company(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Engineer", company=None)
    b = _add_item(sid, "b", "Engineer", company="")
    c = _add_item(sid, "c", "Engineer", company="Acme")
    _add_score(a, pid, 80)
    _add_score(b, pid, 70)
    _add_score(c, pid, 60)

    result = get_today_queue("p1")
    assert len(result) == 3
    assert all(r["similar_count"] == 0 for r in result)


def test_get_today_queue_includes_top_3_matched_terms(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Item X")
    matched = [
        {"term": "python", "kind": "skill", "weight": 3,
         "occurrences": 1, "contribution": 9, "in_title": False},
        {"term": "sql", "kind": "skill", "weight": 3,
         "occurrences": 1, "contribution": 6, "in_title": False},
        {"term": "data analyst", "kind": "role", "weight": 4,
         "occurrences": 1, "contribution": 32, "in_title": False},
        {"term": "java", "kind": "skill", "weight": 3,
         "occurrences": 1, "contribution": 3, "in_title": False},
        {"term": "git", "kind": "skill", "weight": 3,
         "occurrences": 1, "contribution": 1, "in_title": False},
    ]
    _add_score(iid, pid, 100, matched_terms=matched)

    result = get_today_queue("p1")
    assert len(result) == 1
    top_terms = result[0]["top_matched_terms"]
    assert len(top_terms) == 3
    # Sorted by contribution descending: data analyst(32), python(9), sql(6)
    assert top_terms == ["data analyst", "python", "sql"]


# ----- set_status -----


def test_set_status_creates_new_tracking_row(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Item X")

    tracking = set_status(iid, pid, "interested")
    assert tracking.status == TrackingStatus.interested

    with get_session() as session:
        rows = (
            session.execute(select(Tracking).where(Tracking.item_id == iid))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].status == TrackingStatus.interested


def test_set_status_updates_existing_tracking_row(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Item X")

    set_status(iid, pid, "interested")
    set_status(iid, pid, "applied")

    with get_session() as session:
        rows = (
            session.execute(select(Tracking).where(Tracking.item_id == iid))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].status == TrackingStatus.applied


def test_set_status_applied_sets_applied_at(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Item X")

    before = _now()
    tracking = set_status(iid, pid, "applied")
    after = _now()

    assert tracking.applied_at is not None
    assert before <= tracking.applied_at <= after


def test_set_status_applied_does_not_overwrite_applied_at(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Item X")

    first = set_status(iid, pid, "applied")
    first_applied_at = first.applied_at

    time.sleep(0.01)

    second = set_status(iid, pid, "applied")
    assert second.applied_at == first_applied_at


# ----- update_notes -----


def test_update_notes_creates_tracking_with_default_status(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Item X")

    tracking = update_notes(iid, pid, "first notes")
    assert tracking.status == TrackingStatus.interested
    assert tracking.notes == "first notes"


# ----- get_pipeline -----


def test_get_pipeline_groups_by_status(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    items = [_add_item(sid, str(i), f"Item {i}") for i in range(1, 6)]
    for iid in items[:2]:
        _add_tracking(iid, pid, "interested")
    for iid in items[2:4]:
        _add_tracking(iid, pid, "applied")
    _add_tracking(items[4], pid, "phone_screen")

    pipeline = get_pipeline("p1")
    assert len(pipeline["interested"]) == 2
    assert len(pipeline["applied"]) == 2
    assert len(pipeline["phone_screen"]) == 1
    assert len(pipeline["interview"]) == 0
    assert len(pipeline["offer"]) == 0


# ----- get_stats -----


def test_get_stats_response_rate_calculation(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    items = [_add_item(sid, str(i), f"Item {i}") for i in range(1, 9)]
    # 5 in applied, 2 in phone_screen, 1 in interview
    for iid in items[:5]:
        _add_tracking(iid, pid, "applied", applied_at=_now())
    for iid in items[5:7]:
        _add_tracking(iid, pid, "phone_screen")
    _add_tracking(items[7], pid, "interview")

    stats = get_stats("p1")
    assert stats["response_rate"] == pytest.approx(0.6)


def test_get_stats_response_rate_zero_when_no_applications(basic_setup):
    stats = get_stats("p1")
    assert stats["response_rate"] == 0.0


def test_get_stats_applications_this_week_filter(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    yesterday = _now() - timedelta(days=1)
    ten_days_ago = _now() - timedelta(days=10)

    for i in range(1, 4):
        iid = _add_item(sid, f"recent-{i}", f"Recent {i}")
        _add_tracking(iid, pid, "applied", applied_at=yesterday)

    for i in range(1, 3):
        iid = _add_item(sid, f"old-{i}", f"Old {i}")
        _add_tracking(iid, pid, "applied", applied_at=ten_days_ago)

    stats = get_stats("p1")
    assert stats["applications_this_week"] == 3
