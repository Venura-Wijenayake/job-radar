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
    summary = seed_antikeywords("p1")
    assert summary["added"] == len(ANTI_KEYWORDS)
    assert summary["skipped"] == 0

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
        assert r.weight == 2
        assert r.source == "manual"


def test_idempotent_on_second_run(profile_p1):
    seed_antikeywords("p1")
    second = seed_antikeywords("p1")
    assert second["added"] == 0
    assert second["skipped"] == len(ANTI_KEYWORDS)

    with get_session() as session:
        rows = (
            session.execute(
                select(Criterion).where(Criterion.kind == "exclude")
            )
            .scalars()
            .all()
        )
    assert len(rows) == len(ANTI_KEYWORDS)


def test_partial_idempotency_after_one_manually_inserted(profile_p1):
    """If one anti-keyword already exists, the seed adds the rest and
    skips the duplicate."""
    with get_session() as session:
        session.add(
            Criterion(
                profile_id=profile_p1,
                term="senior",
                kind="exclude",
                weight=2,
                source="manual",
            )
        )
        session.commit()

    summary = seed_antikeywords("p1")
    assert summary["added"] == len(ANTI_KEYWORDS) - 1
    assert summary["skipped"] == 1


def test_unknown_profile_raises(fresh_db):
    with pytest.raises(ValueError, match="Profile not found"):
        seed_antikeywords("nonexistent")
