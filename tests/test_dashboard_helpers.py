"""Tests for dashboard.data helpers — pure SQLAlchemy, no Streamlit."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from dashboard.data import (
    EXAMPLE_PHRASING,
    _generate_example_phrasing,
    add_manual_criterion,
    get_pipeline,
    get_profile_summary,
    get_resume_tailor_view,
    get_stats,
    get_today_queue,
    list_manual_criteria,
    list_taxonomy,
    remove_manual_criterion,
    set_status,
    update_notes,
)
from db.database import get_session
from db.models import (
    Criterion,
    Item,
    KeywordExtract,
    Profile,
    Score,
    Source,
    Tracking,
    TrackingStatus,
)


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
    location_normalized: str | None = None,
    language_detected: str | None = None,
    citizenship_required: bool | None = None,
    license_required: bool | None = None,
    ghost_score: int | None = None,
    geo_tier: str | None = None,
) -> int:
    metadata: dict = {}
    if company:
        metadata["company"] = company
    if location_normalized is not None:
        metadata["location_normalized"] = location_normalized
    if language_detected is not None:
        metadata["language_detected"] = language_detected
    if citizenship_required is not None:
        metadata["citizenship_required"] = citizenship_required
    if license_required is not None:
        metadata["license_required"] = license_required
    if ghost_score is not None:
        metadata["ghost_score"] = ghost_score
    if geo_tier is not None:
        metadata["geo_tier"] = geo_tier
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
            metadata_json=metadata,
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


def test_get_today_queue_filters_by_location(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", location_normalized="US")
    b = _add_item(sid, "b", "Item B", company="Beta", location_normalized="US")
    c = _add_item(sid, "c", "Item C", company="Brasil Inc", location_normalized="Brazil")
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 50)

    result = get_today_queue("p1", allowed_locations=["US"])
    assert len(result) == 2
    assert {r["item_id"] for r in result} == {a, b}


def test_get_today_queue_filters_unknown_location_lenient(basic_setup):
    """Items with location_normalized='Unknown' (or missing) are kept even
    when allowed_locations is set. Better to surface ambiguous items than
    hide them."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", location_normalized="US")
    b = _add_item(sid, "b", "Item B", company="Beta", location_normalized="Unknown")
    c = _add_item(sid, "c", "Item C", company="Gamma", location_normalized="Brazil")
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 50)

    result = get_today_queue("p1", allowed_locations=["US"])
    assert len(result) == 2
    assert {r["item_id"] for r in result} == {a, b}


def test_get_today_queue_filters_foreign_by_default(basic_setup):
    """Items with geo_tier='foreign' are dropped at default settings —
    profile metadata's allowed_geo_tiers excludes 'foreign'."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.id == pid)
        ).scalar_one()
        profile.metadata_json = {
            "allowed_geo_tiers": ["local", "regional", "domestic", "unknown"],
        }
        session.commit()

    a = _add_item(sid, "a", "Local Item", company="Acme", geo_tier="local")
    b = _add_item(sid, "b", "Domestic Item", company="Beta", geo_tier="domestic")
    c = _add_item(sid, "c", "Foreign Item", company="Gamma", geo_tier="foreign")
    d = _add_item(sid, "d", "Unknown Item", company="Delta", geo_tier="unknown")
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 90)  # high score but should still be filtered out
    _add_score(d, pid, 50)

    result = get_today_queue("p1")
    item_ids = {r["item_id"] for r in result}
    assert c not in item_ids
    assert {a, b, d} == item_ids


def test_get_today_queue_includes_foreign_when_explicitly_allowed(basic_setup):
    """When the caller passes allowed_geo_tiers including 'foreign',
    foreign items appear in the queue."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Local Item", company="Acme", geo_tier="local")
    b = _add_item(sid, "b", "Foreign Item", company="Beta", geo_tier="foreign")
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue(
        "p1",
        allowed_geo_tiers=["local", "regional", "domestic", "unknown", "foreign"],
    )
    assert {r["item_id"] for r in result} == {a, b}


def test_get_today_queue_foreign_filter_uses_profile_metadata_default(basic_setup):
    """When the profile has no allowed_geo_tiers metadata, the function
    still defaults to excluding 'foreign'."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    # Profile metadata is empty — no allowed_geo_tiers key
    a = _add_item(sid, "a", "Local Item", company="Acme", geo_tier="local")
    b = _add_item(sid, "b", "Foreign Item", company="Beta", geo_tier="foreign")
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1")
    assert {r["item_id"] for r in result} == {a}


def test_geo_boost_local_outranks_higher_score_domestic(basic_setup):
    """Local item raw 60 + boost 20 = 80 should outrank domestic item
    raw 70 + boost 0 = 70."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.id == pid)
        ).scalar_one()
        profile.metadata_json = {
            "geo_boost_local": 20,
            "geo_boost_regional": 10,
            "geo_boost_domestic": 0,
        }
        session.commit()

    a = _add_item(sid, "a", "Local Item", company="Acme", geo_tier="local")
    b = _add_item(sid, "b", "Domestic Item", company="Beta", geo_tier="domestic")
    _add_score(a, pid, 60)
    _add_score(b, pid, 70)

    result = get_today_queue("p1")
    item_ids = [r["item_id"] for r in result]
    assert item_ids[0] == a, f"expected local first; got {item_ids}"
    assert item_ids[1] == b
    # display_score reflects the boost
    by_id = {r["item_id"]: r for r in result}
    assert by_id[a]["display_score"] == 80
    assert by_id[a]["geo_boost_applied"] == 20
    assert by_id[b]["display_score"] == 70
    assert by_id[b]["geo_boost_applied"] == 0


def test_geo_boost_does_not_modify_db_score(basic_setup):
    """The persisted scores.score row should be unchanged after a queue
    call, even though the returned dict has a boosted display_score."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.id == pid)
        ).scalar_one()
        profile.metadata_json = {"geo_boost_local": 20}
        session.commit()

    a = _add_item(sid, "a", "Local", company="Acme", geo_tier="local")
    _add_score(a, pid, 70.0)

    result = get_today_queue("p1")
    assert result[0]["score"] == 70.0
    assert result[0]["display_score"] == 90.0
    assert result[0]["geo_boost_applied"] == 20

    with get_session() as session:
        score_row = session.execute(select(Score)).scalar_one()
    assert score_row.score == 70.0  # DB row unchanged


def test_get_today_queue_filters_old_items(basic_setup):
    """Items whose posted_at is older than posted_after_days drop out;
    items with NULL posted_at are kept (unknown != stale)."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    fresh = _now() - timedelta(days=5)
    stale = _now() - timedelta(days=60)

    a = _add_item(sid, "a", "Fresh", company="Acme", posted_at=fresh)
    b = _add_item(sid, "b", "Stale", company="Beta", posted_at=stale)
    c = _add_item(sid, "c", "NoDate", company="Gamma")  # posted_at = None
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 50)

    result = get_today_queue("p1", posted_after_days=30)
    assert {r["item_id"] for r in result} == {a, c}


def test_get_today_queue_recency_from_profile_metadata(basic_setup):
    """When posted_after_days is None, fall back to profile.metadata_json."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.id == pid)
        ).scalar_one()
        profile.metadata_json = {"posted_after_days": 7}
        session.commit()

    fresh = _now() - timedelta(days=3)
    stale = _now() - timedelta(days=20)
    a = _add_item(sid, "a", "Fresh", company="Acme", posted_at=fresh)
    b = _add_item(sid, "b", "Stale", company="Beta", posted_at=stale)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1")  # no explicit param — read from profile
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_hides_citizenship_required(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", citizenship_required=False)
    b = _add_item(sid, "b", "Item B", company="Beta", citizenship_required=True)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1", hide_citizenship_required=True)
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_shows_citizenship_required_when_disabled(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", citizenship_required=False)
    b = _add_item(sid, "b", "Item B", company="Beta", citizenship_required=True)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1", hide_citizenship_required=False)
    assert {r["item_id"] for r in result} == {a, b}


def test_get_today_queue_hides_license_required(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", license_required=False)
    b = _add_item(sid, "b", "Item B", company="Beta", license_required=True)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1", hide_license_required=True)
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_hides_high_ghost_score(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", ghost_score=10)
    b = _add_item(sid, "b", "Item B", company="Beta", ghost_score=90)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1", hide_ghost_jobs_above=80)
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_shows_warning_for_medium_ghost_score(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", ghost_score=10)
    b = _add_item(sid, "b", "Item B", company="Beta", ghost_score=65)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)

    result = get_today_queue("p1", hide_ghost_jobs_above=80)
    by_id = {r["item_id"]: r for r in result}
    assert by_id[a]["ghost_warning"] is False
    assert by_id[b]["ghost_warning"] is True


def test_get_today_queue_filters_from_profile_metadata(basic_setup):
    """When the new params are None, fall back to profile.metadata_json."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.id == pid)
        ).scalar_one()
        profile.metadata_json = {
            "hide_citizenship_required": True,
            "hide_license_required": False,
            "hide_ghost_jobs_above": 50,  # tighter threshold
        }
        session.commit()

    a = _add_item(sid, "a", "Item A", company="Acme",
                   citizenship_required=False, ghost_score=10)
    b = _add_item(sid, "b", "Item B", company="Beta",
                   citizenship_required=True, ghost_score=10)
    c = _add_item(sid, "c", "Item C", company="Gamma",
                   citizenship_required=False, ghost_score=70)
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 50)

    result = get_today_queue("p1")  # no explicit overrides
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_english_only_drops_other(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Item A", company="Acme", language_detected="en")
    b = _add_item(sid, "b", "Item B", company="Beta", language_detected="other")
    c = _add_item(sid, "c", "Item C", company="Gamma", language_detected="mixed")
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 50)

    result = get_today_queue("p1", english_only=True)
    assert {r["item_id"] for r in result} == {a, c}


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


def test_get_today_queue_includes_fit_tier_in_results(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Data Analyst", body="great role")
    b = _add_item(sid, "b", "Senior Staff Data Analyst", body="10+ years required")
    _add_score(a, pid, 85)
    _add_score(b, pid, 85)

    result = get_today_queue("p1")
    by_id = {r["item_id"]: r for r in result}
    # Plain title, score 85 → high_fit
    assert by_id[a]["fit_tier"] == "high_fit"
    # Two title flags + body experience flag → long_shot
    assert by_id[b]["fit_tier"] == "long_shot"


def test_get_today_queue_filter_by_fit_tier_excludes_others(basic_setup):
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Data Analyst", company="Acme")          # high_fit
    b = _add_item(sid, "b", "Senior Data Analyst", company="Beta")    # stretch
    c = _add_item(sid, "c", "Senior Staff Analyst",
                  body="10+ years required", company="Gamma")          # long_shot
    _add_score(a, pid, 85)
    _add_score(b, pid, 85)
    _add_score(c, pid, 85)

    result = get_today_queue("p1", allowed_fit_tiers=["high_fit"])
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_default_includes_all_fit_tiers(basic_setup):
    """No profile metadata, no explicit param — all three tiers appear."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    a = _add_item(sid, "a", "Data Analyst", company="Acme")          # high_fit
    b = _add_item(sid, "b", "Senior Data Analyst", company="Beta")   # stretch
    c = _add_item(sid, "c", "Senior Staff Analyst",
                  body="10+ years required", company="Gamma")         # long_shot
    _add_score(a, pid, 85)
    _add_score(b, pid, 85)
    _add_score(c, pid, 85)

    result = get_today_queue("p1")
    assert {r["item_id"] for r in result} == {a, b, c}
    tiers = {r["fit_tier"] for r in result}
    assert tiers == {"high_fit", "stretch", "long_shot"}


def test_get_today_queue_fit_tier_filter_uses_profile_metadata(basic_setup):
    """When allowed_fit_tiers param is None, profile metadata controls."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.id == pid)
        ).scalar_one()
        profile.metadata_json = {"allowed_fit_tiers": ["high_fit"]}
        session.commit()

    a = _add_item(sid, "a", "Data Analyst", company="Acme")          # high_fit
    b = _add_item(sid, "b", "Senior Data Analyst", company="Beta")   # stretch
    _add_score(a, pid, 85)
    _add_score(b, pid, 85)

    result = get_today_queue("p1")
    assert {r["item_id"] for r in result} == {a}


def test_get_today_queue_includes_top_strong_and_top_missing(basic_setup):
    """top_strong = JD keywords that are in resume criteria, ranked by
    JD freq × importance. top_missing = JD keywords NOT in criteria,
    same ranking. Each truncated to 3."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    _add_criterion(pid, "python", kind="skill")
    _add_criterion(pid, "sql", kind="skill")
    _add_criterion(pid, "pandas", kind="skill")

    iid = _add_item(sid, "x", "Data Analyst", company="Acme")
    _add_score(iid, pid, 70)
    _add_keyword_extract(
        iid,
        [
            {"term": "python", "frequency": 5, "importance": 2.0},   # 10
            {"term": "sql", "frequency": 4, "importance": 1.5},      # 6
            {"term": "pandas", "frequency": 1, "importance": 1.0},   # 1
            {"term": "tableau", "frequency": 6, "importance": 2.0},  # 12
            {"term": "snowflake", "frequency": 3, "importance": 2.0},# 6
            {"term": "dbt", "frequency": 1, "importance": 1.0},      # 1
        ],
    )

    result = get_today_queue("p1")
    assert len(result) == 1
    row = result[0]
    # Strong terms sorted desc by rank: python(10), sql(6), pandas(1)
    assert row["top_strong"] == ["python", "sql", "pandas"]
    # Missing terms sorted desc by rank: tableau(12), snowflake(6), dbt(1)
    assert row["top_missing"] == ["tableau", "snowflake", "dbt"]


def test_get_today_queue_top_strong_missing_default_empty_when_no_extracts(basic_setup):
    """Items without keyword_extracts get empty lists rather than missing keys."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    iid = _add_item(sid, "x", "Data Analyst")
    _add_score(iid, pid, 70)

    result = get_today_queue("p1")
    assert result[0]["top_strong"] == []
    assert result[0]["top_missing"] == []


def test_get_today_queue_posted_after_24h_filter(basic_setup):
    """posted_after_days=1 keeps items posted within the last day,
    drops items older than 24h. Items with NULL posted_at are kept."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    fresh = _now() - timedelta(hours=12)
    yesterday = _now() - timedelta(days=2)
    a = _add_item(sid, "a", "Fresh", company="Acme", posted_at=fresh)
    b = _add_item(sid, "b", "Old", company="Beta", posted_at=yesterday)
    c = _add_item(sid, "c", "NoDate", company="Gamma")  # NULL posted_at
    _add_score(a, pid, 70)
    _add_score(b, pid, 60)
    _add_score(c, pid, 50)

    result = get_today_queue("p1", posted_after_days=1)
    assert {r["item_id"] for r in result} == {a, c}


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


# ----- Resume Tailor -----


def _add_resume_text(profile_id: int, text: str) -> None:
    with get_session() as session:
        p = session.execute(
            select(Profile).where(Profile.id == profile_id)
        ).scalar_one()
        p.resume_raw_text = text
        session.commit()


def _add_criterion(
    profile_id: int, term: str, kind: str = "skill", weight: int = 3,
    source: str = "resume",
) -> int:
    with get_session() as session:
        c = Criterion(
            profile_id=profile_id,
            term=term,
            kind=kind,
            weight=weight,
            source=source,
            match_type="fuzzy",
        )
        session.add(c)
        session.commit()
        return c.id


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


def _add_score_full(item_id: int, profile_id: int, score: float) -> None:
    with get_session() as session:
        session.add(
            Score(
                item_id=item_id,
                profile_id=profile_id,
                score=score,
                raw_score=score,
                matched_terms_json=[],
                computed_at=_now(),
            )
        )
        session.commit()


def test_resume_tailor_diff_have_strong(basic_setup):
    """A JD keyword that's in resume criteria AND appears >=2 times in
    resume text -> have_strong."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    _add_resume_text(pid, "I use python daily. Python is my main language. python.")
    _add_criterion(pid, "python", kind="skill", weight=3)

    iid = _add_item(sid, "x", "Engineer", body="we use python")
    _add_score_full(iid, pid, 50.0)
    _add_keyword_extract(
        iid, [{"term": "python", "frequency": 3, "importance": 2.0}]
    )

    view = get_resume_tailor_view(iid, "p1")
    terms = [k["term"] for k in view["diff"]["have_strong"]]
    assert "python" in terms


def test_resume_tailor_diff_have_buried(basic_setup):
    """A JD keyword in resume criteria but appearing <2 times in resume text
    -> have_buried."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    _add_resume_text(pid, "Brief mention of tableau once.")
    _add_criterion(pid, "tableau", kind="skill", weight=3)

    iid = _add_item(sid, "x", "Analyst", body="tableau dashboards")
    _add_score_full(iid, pid, 30.0)
    _add_keyword_extract(
        iid, [{"term": "tableau", "frequency": 5, "importance": 2.0}]
    )

    view = get_resume_tailor_view(iid, "p1")
    terms = [k["term"] for k in view["diff"]["have_buried"]]
    assert "tableau" in terms
    strong_terms = [k["term"] for k in view["diff"]["have_strong"]]
    assert "tableau" not in strong_terms


def test_resume_tailor_diff_missing_sorted_by_importance(basic_setup):
    """JD keywords NOT in resume criteria are sorted by frequency*importance
    descending."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    _add_resume_text(pid, "I use python.")
    _add_criterion(pid, "python", kind="skill")

    iid = _add_item(sid, "x", "T", body="various tools")
    _add_score_full(iid, pid, 50.0)
    _add_keyword_extract(
        iid,
        [
            {"term": "python", "frequency": 2, "importance": 2.0},   # not missing
            {"term": "kubernetes", "frequency": 1, "importance": 1.0},  # 1.0
            {"term": "snowflake", "frequency": 4, "importance": 2.0},  # 8.0
            {"term": "bigquery", "frequency": 2, "importance": 2.0},   # 4.0
        ],
    )
    view = get_resume_tailor_view(iid, "p1")
    missing_terms = [k["term"] for k in view["diff"]["missing"]]
    assert missing_terms == ["snowflake", "bigquery", "kubernetes"]


def test_resume_tailor_suggested_rewrites_uses_template(basic_setup):
    """A JD keyword present in EXAMPLE_PHRASING gets the template phrasing."""
    sid, pid = basic_setup["source_id"], basic_setup["profile_id"]
    _add_resume_text(pid, "python python python")
    _add_criterion(pid, "python", kind="skill")

    iid = _add_item(sid, "x", "T", body="snowflake required")
    _add_score_full(iid, pid, 50.0)
    _add_keyword_extract(
        iid, [{"term": "snowflake", "frequency": 5, "importance": 2.0}]
    )

    view = get_resume_tailor_view(iid, "p1")
    snowflake_rw = next(
        r for r in view["suggested_rewrites"] if r["term"] == "snowflake"
    )
    assert snowflake_rw["example_phrasing"] == EXAMPLE_PHRASING["snowflake"]
    assert snowflake_rw["category"] == "missing"


def test_resume_tailor_suggested_rewrites_falls_back():
    """An unknown term gets the generic phrasing fallback."""
    out = _generate_example_phrasing("zzznot_a_real_skill")
    assert "zzznot_a_real_skill" in out
    assert "Consider adding a bullet" in out


# ----- Settings -----


def test_add_manual_criterion_creates_row(basic_setup):
    pid = basic_setup["profile_id"]
    row = add_manual_criterion("p1", "tableau", "skill", 3)
    assert row is not None
    assert row.term == "tableau"
    assert row.source == "manual"


def test_add_manual_criterion_idempotent(basic_setup):
    pid = basic_setup["profile_id"]
    first = add_manual_criterion("p1", "tableau", "skill", 3)
    second = add_manual_criterion("p1", "tableau", "skill", 3)
    assert first is not None
    assert second is None  # already exists


def test_remove_manual_criterion_only_deletes_manual_source(basic_setup):
    pid = basic_setup["profile_id"]
    row = add_manual_criterion("p1", "tableau", "skill", 3)
    assert row is not None
    ok = remove_manual_criterion("p1", row.id)
    assert ok is True
    assert list_manual_criteria("p1") == []


def test_remove_manual_criterion_refuses_resume_source(basic_setup):
    pid = basic_setup["profile_id"]
    cid = _add_criterion(pid, "python", kind="skill", source="resume")
    ok = remove_manual_criterion("p1", cid)
    assert ok is False
    # Confirm row still exists
    with get_session() as session:
        still = session.execute(
            select(Criterion).where(Criterion.id == cid)
        ).scalar_one_or_none()
    assert still is not None


def test_get_profile_summary_returns_correct_counts(basic_setup):
    pid = basic_setup["profile_id"]
    _add_criterion(pid, "python", kind="skill", source="resume")
    _add_criterion(pid, "sql", kind="skill", source="resume")
    _add_criterion(pid, "data analyst", kind="role", source="resume")
    add_manual_criterion("p1", "tableau", "skill", 3)
    add_manual_criterion("p1", "vp", "exclude", 3)

    summary = get_profile_summary("p1")
    counts = summary["criteria_counts_by_kind"]
    assert counts.get("skill") == 3
    assert counts.get("role") == 1
    assert counts.get("exclude") == 1


def test_list_taxonomy_returns_dict():
    tax = list_taxonomy()
    assert isinstance(tax, dict)
    assert "skills" in tax
    assert "roles" in tax
