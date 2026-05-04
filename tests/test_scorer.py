"""Phase 4.7: scorer.py is a thin shim over match_score_v2.

The original v1 tests exercised implementation details (8x role base,
3x skill cap, -10x exclude penalty) that the v2 split-component
formula no longer applies. These tests now verify the persisted-side
behaviour of the v2 scorer:

  - Scores are floored at 0 and capped at 100.
  - Items with no signals never produce negative scores.
  - Upsert keeps a single Score row per (item, profile).
  - HTML stripping happens before matching (no <p>...</p> noise).
  - The matched-terms list is populated.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from db.database import get_session
from db.models import Criterion, Item, Profile, Score, Source
from scoring.scorer import score_item


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_source(session) -> Source:
    src = Source(name="Test", type="api", url="http://test", enabled=True)
    session.add(src)
    session.flush()
    return src


def _make_profile(session, parsed_at=None) -> Profile:
    p = Profile(name="test_profile", parsed_at=parsed_at or _now())
    session.add(p)
    session.flush()
    return p


def _add_criterion(session, profile_id, term, kind, weight=3, weight_tier=2):
    c = Criterion(
        profile_id=profile_id, term=term, kind=kind, weight=weight,
        weight_tier=weight_tier, match_type="fuzzy", source="resume",
    )
    session.add(c)
    session.flush()
    return c


def _make_item(session, source_id, *, title, body, ext_id="x") -> Item:
    item = Item(
        source_id=source_id, external_id=ext_id, title=title, body=body,
        url=f"http://test/{ext_id}", content_hash=f"hash-{ext_id}",
        scraped_at=_now(),
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture()
def setup_basic(fresh_db):
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        _add_criterion(session, profile.id, "data analyst", "role", weight=4)
        _add_criterion(session, profile.id, "python", "skill", weight=3, weight_tier=1)
        session.commit()
        return {"source_id": src.id, "profile_id": profile.id}


def test_score_caps_at_100(setup_basic):
    """A perfect-fit item — title role match + many skills — saturates at
    or below 100, never above."""
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Senior Data Analyst",
            body="python python python data analyst with sql excel git github pandas jupyter",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        s = score_item(item, profile, session)
        session.commit()

    assert 0.0 <= s.score <= 100.0


def test_score_floors_at_zero_with_no_signal(fresh_db):
    """Item that doesn't match any criterion stays >=0 — never negative."""
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        _add_criterion(session, profile.id, "python", "skill", weight=3)
        session.commit()
        item = _make_item(session, src.id, title="zzqq", body="qqzz nothing here")
        s = score_item(item, profile, session)
        session.commit()

    assert s.score >= 0.0


def test_zero_criteria_yields_low_or_zero_score(fresh_db):
    """No criteria at all → no role/skill/keyword signal → low score
    (only the default title_family contributes its 7.5 floor)."""
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        session.commit()
        item = _make_item(session, src.id, title="anything", body="anything")
        s = score_item(item, profile, session)
        session.commit()

    assert 0.0 <= s.score <= 10.0


def test_role_title_match_contributes(setup_basic):
    """A title-level role match should deliver the role sub-score in
    full and produce a meaningfully positive total."""
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Senior Data Analyst",
            body="Looking for a strong data analyst.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        s = score_item(item, profile, session)
        session.commit()

    # Role 1.0 × 0.35 + family (data_analyst_exact) 1.0 × 0.15 = 0.50
    # plus skill density depending on body. Lower bound 35.
    assert s.score >= 35.0


def test_skill_only_match_contributes_via_skill_subscore(setup_basic):
    """An item with only skill matches (no title role) gets a positive
    score from the 40% skill weight."""
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Engineer",
            body="We use python every day.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        s = score_item(item, profile, session)
        session.commit()

    assert s.score > 0.0


def test_role_in_title_outranks_role_in_body_only(setup_basic):
    """Same body content; one item has the role in the title, the other
    doesn't. The title-match should score higher (1.0 vs 0.5 role
    sub-score) under v2."""
    with get_session() as session:
        item_title = _make_item(
            session, setup_basic["source_id"], ext_id="t",
            title="Data Analyst",
            body="Hiring a data analyst for the team. python.",
        )
        item_body = _make_item(
            session, setup_basic["source_id"], ext_id="b",
            title="Engineer",
            body="Hiring a data analyst for the team. python.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        s_title = score_item(item_title, profile, session)
        s_body = score_item(item_body, profile, session)
        session.commit()

    assert s_title.score > s_body.score


def test_upsert_updates_existing_row(setup_basic):
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Engineer", body="python",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score_item(item, profile, session)
        session.commit()

        first_count = session.execute(select(Score)).scalars().all()
        assert len(first_count) == 1

        score_item(item, profile, session)
        session.commit()

        second_count = session.execute(select(Score)).scalars().all()
        assert len(second_count) == 1


def test_strips_html_before_matching(setup_basic):
    """HTML tags in title/body shouldn't break term matching."""
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="<b>Data Analyst</b>",
            body="<p>We use <strong>python</strong> and SQL.</p>",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        s = score_item(item, profile, session)
        session.commit()

    # Title role match works through the <b> tags, body skill match too.
    matched_terms = [t["term"] for t in (s.matched_terms_json or [])]
    assert "python" in matched_terms


def test_matched_terms_list_populated(setup_basic):
    """Each scored item carries a list of matched-term descriptors so
    the dashboard's top_matched_terms field can render."""
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Data Analyst",
            body="python python python data analyst",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        s = score_item(item, profile, session)
        session.commit()

    assert isinstance(s.matched_terms_json, list)
    assert len(s.matched_terms_json) > 0
