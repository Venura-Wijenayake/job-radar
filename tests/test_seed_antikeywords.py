from __future__ import annotations

import pytest
from sqlalchemy import select

from db.database import get_session
from db.models import Criterion, Profile
from scripts.seed_antikeywords import ANTI_KEYWORDS, seed_antikeywords


@pytest.fixture()
def profile_p1(fresh_db):
    with get_session() as session:
        profile = Profile(name="p1")
        session.add(profile)
        session.commit()
        return profile.id


def test_seeds_all_anti_keywords(profile_p1):
    from scripts.seed_antikeywords import HIGH_PENALTY_TERMS

    summary = seed_antikeywords("p1")
    assert summary["added"] == len(ANTI_KEYWORDS)
    assert summary["updated"] == 0
    assert summary["unchanged"] == 0

    with get_session() as session:
        rows = (
            session.execute(
                select(Criterion).where(Criterion.kind == "exclude")
            )
            .scalars()
            .all()
        )
    terms = {r.term for r in rows}
    assert terms == set(ANTI_KEYWORDS)
    for r in rows:
        expected = 3 if r.term in HIGH_PENALTY_TERMS else 2
        assert r.weight == expected, f"{r.term} weight={r.weight}, want {expected}"
        assert r.source == "manual"


def test_idempotent_on_second_run(profile_p1):
    seed_antikeywords("p1")
    second = seed_antikeywords("p1")
    assert second["added"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == len(ANTI_KEYWORDS)


def test_partial_idempotency_after_one_manually_inserted(profile_p1):
    """If one anti-keyword already exists at the desired weight, the seed
    adds the rest and leaves the existing one unchanged."""
    with get_session() as session:
        session.add(
            Criterion(
                profile_id=profile_p1,
                term="senior",  # not in HIGH_PENALTY_TERMS, desired weight=2
                kind="exclude",
                weight=2,
                source="manual",
            )
        )
        session.commit()

    summary = seed_antikeywords("p1")
    assert summary["added"] == len(ANTI_KEYWORDS) - 1
    assert summary["updated"] == 0
    assert summary["unchanged"] == 1


def test_existing_low_weight_high_penalty_term_gets_bumped(profile_p1):
    """A pre-existing 'manager' criterion at weight=2 should be updated to
    weight=3 by the new seed (HIGH_PENALTY_TERMS bump)."""
    with get_session() as session:
        session.add(
            Criterion(
                profile_id=profile_p1,
                term="manager",
                kind="exclude",
                weight=2,
                source="manual",
            )
        )
        session.commit()

    summary = seed_antikeywords("p1")
    assert summary["updated"] == 1

    with get_session() as session:
        row = session.execute(
            select(Criterion).where(Criterion.term == "manager")
        ).scalar_one()
    assert row.weight == 3


def test_unknown_profile_raises(fresh_db):
    with pytest.raises(ValueError, match="Profile not found"):
        seed_antikeywords("nonexistent")
