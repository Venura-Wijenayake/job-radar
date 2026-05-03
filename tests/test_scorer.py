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


def _add_criterion(session, profile_id, term, kind, weight=3) -> Criterion:
    c = Criterion(
        profile_id=profile_id,
        term=term,
        kind=kind,
        weight=weight,
        match_type="fuzzy",
        source="resume",
    )
    session.add(c)
    session.flush()
    return c


def _make_item(session, source_id, *, title, body, ext_id="x") -> Item:
    item = Item(
        source_id=source_id,
        external_id=ext_id,
        title=title,
        body=body,
        url=f"http://test/{ext_id}",
        content_hash=f"hash-{ext_id}",
        scraped_at=_now(),
    )
    session.add(item)
    session.flush()
    return item


@pytest.fixture()
def setup_basic(fresh_db):
    """Profile with one role + one skill, returns ids for use in test."""
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        _add_criterion(session, profile.id, "data analyst", "role", weight=4)
        _add_criterion(session, profile.id, "python", "skill", weight=3)
        session.commit()
        return {"source_id": src.id, "profile_id": profile.id}


def test_skill_single_occurrence(setup_basic):
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Engineer", body="We use python.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score = score_item(item, profile, session)
        session.commit()

    skill_match = next(t for t in score.matched_terms_json if t["term"] == "python")
    assert skill_match["occurrences"] == 1
    assert skill_match["contribution"] == 1 * 3


def test_skill_caps_occurrences_at_three(setup_basic):
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Engineer",
            body="python python python python python python.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score = score_item(item, profile, session)
        session.commit()

    skill_match = next(t for t in score.matched_terms_json if t["term"] == "python")
    assert skill_match["occurrences"] == 6
    assert skill_match["contribution"] == 3 * 3


def test_role_match_in_body_only(setup_basic):
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Engineer",
            body="Hiring a data analyst for the team.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score = score_item(item, profile, session)
        session.commit()

    role_match = next(t for t in score.matched_terms_json if t["term"] == "data analyst")
    assert role_match["in_title"] is False
    assert role_match["contribution"] == 8 * 4


def test_role_title_boost(setup_basic):
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Senior Data Analyst",
            body="Looking for a strong data analyst.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score = score_item(item, profile, session)
        session.commit()

    role_match = next(t for t in score.matched_terms_json if t["term"] == "data analyst")
    assert role_match["in_title"] is True
    assert role_match["contribution"] == 8 * 4 * 2


def test_exclude_kind_penalizes(fresh_db):
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        _add_criterion(session, profile.id, "python", "skill", weight=3)
        _add_criterion(session, profile.id, "php", "exclude", weight=2)
        session.commit()
        item = _make_item(
            session, src.id, title="Engineer", body="python and php developer."
        )
        score = score_item(item, profile, session)
        session.commit()

    excl_match = next(t for t in score.matched_terms_json if t["term"] == "php")
    assert excl_match["contribution"] == -10 * 2


def test_score_floors_at_zero_with_only_negative_signal(fresh_db):
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        _add_criterion(session, profile.id, "php", "exclude", weight=3)
        session.commit()
        item = _make_item(session, src.id, title="PHP role", body="PHP PHP PHP.")
        score = score_item(item, profile, session)
        session.commit()

    assert score.score == 0.0


def test_perfect_match_normalizes_to_100(fresh_db):
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        _add_criterion(session, profile.id, "data analyst", "role", weight=4)
        _add_criterion(session, profile.id, "python", "skill", weight=3)
        session.commit()
        item = _make_item(
            session, src.id,
            title="Senior Data Analyst",
            body="python python python data analyst",
        )
        score = score_item(item, profile, session)
        session.commit()

    assert score.score == 100.0


def test_zero_criteria_yields_zero_score(fresh_db):
    with get_session() as session:
        src = _make_source(session)
        profile = _make_profile(session)
        session.commit()
        item = _make_item(session, src.id, title="anything", body="anything")
        score = score_item(item, profile, session)
        session.commit()

    assert score.score == 0.0
    assert score.matched_terms_json == []


def test_no_matches_yields_zero_score(setup_basic):
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="Plumber",
            body="Fixing pipes.",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score = score_item(item, profile, session)
        session.commit()

    assert score.score == 0.0
    assert score.matched_terms_json == []


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
    with get_session() as session:
        item = _make_item(
            session, setup_basic["source_id"],
            title="<b>Engineer</b>",
            body="<p>We use <strong>python</strong> and SQL.</p>",
        )
        profile = session.get(Profile, setup_basic["profile_id"])
        score = score_item(item, profile, session)
        session.commit()

    py = next(t for t in score.matched_terms_json if t["term"] == "python")
    assert py["occurrences"] == 1
