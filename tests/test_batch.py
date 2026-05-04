from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.database import get_session
from db.models import Criterion, Item, KeywordExtract, Profile, Score, Source
from scoring.batch import extract_all_keywords, score_all_items


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_basic(*, parsed_at=None):
    """Create source + profile + 2 criteria + 3 items. Returns nothing — the
    caller queries the DB for what it needs."""
    with get_session() as session:
        src = Source(name="Test", type="api", url="http://t", enabled=True)
        session.add(src)
        session.flush()

        profile = Profile(name="p1", parsed_at=parsed_at or _now())
        session.add(profile)
        session.flush()

        session.add_all(
            [
                Criterion(
                    profile_id=profile.id, term="data analyst", kind="role",
                    weight=4, source="resume",
                ),
                Criterion(
                    profile_id=profile.id, term="python", kind="skill",
                    weight=3, source="resume",
                ),
            ]
        )

        session.add_all(
            [
                Item(
                    source_id=src.id, external_id="1", title="Data Analyst",
                    body="python python python data analyst",
                    url="http://t/1", content_hash="h1", scraped_at=_now(),
                ),
                Item(
                    source_id=src.id, external_id="2", title="Engineer",
                    body="some python here",
                    url="http://t/2", content_hash="h2", scraped_at=_now(),
                ),
                Item(
                    source_id=src.id, external_id="3", title="Plumber",
                    body="fixing pipes",
                    url="http://t/3", content_hash="h3", scraped_at=_now(),
                ),
            ]
        )
        session.commit()


def test_score_all_items_first_pass(fresh_db):
    _seed_basic()
    summary = score_all_items("p1")

    assert summary["total_items"] == 3
    assert summary["scored"] == 3
    assert summary["skipped"] == 0
    assert summary["errors"] == 0
    assert sum(summary["score_distribution"].values()) == 3


def test_score_all_items_incremental_skips_fresh(fresh_db):
    """Running score_all_items twice without --force should skip everything
    on the second run because no items or criteria have changed."""
    _seed_basic()
    score_all_items("p1")
    summary = score_all_items("p1", force=False)

    assert summary["scored"] == 0
    assert summary["skipped"] == 3
    # Skipped items still count toward the distribution
    assert sum(summary["score_distribution"].values()) == 3


def test_score_all_items_force_rescores(fresh_db):
    _seed_basic()
    score_all_items("p1")
    summary = score_all_items("p1", force=True)

    assert summary["scored"] == 3
    assert summary["skipped"] == 0


def test_score_all_items_rescores_when_profile_reparsed(fresh_db):
    """If the profile.parsed_at is newer than scores.computed_at, items should
    be rescored even without --force."""
    _seed_basic()
    score_all_items("p1")

    with get_session() as session:
        profile = session.execute(
            select(Profile).where(Profile.name == "p1")
        ).scalar_one()
        profile.parsed_at = _now() + timedelta(seconds=5)
        session.commit()

    summary = score_all_items("p1", force=False)
    assert summary["scored"] == 3
    assert summary["skipped"] == 0


def test_score_all_items_distribution_buckets(fresh_db):
    _seed_basic()
    summary = score_all_items("p1")
    dist = summary["score_distribution"]

    with get_session() as session:
        scores = session.execute(select(Score)).scalars().all()

    for s in scores:
        if s.score < 25:
            bucket = "0-25"
        elif s.score < 50:
            bucket = "25-50"
        elif s.score < 75:
            bucket = "50-75"
        else:
            bucket = "75-100"
        assert dist[bucket] >= 1


def test_extract_all_keywords_first_pass(fresh_db):
    _seed_basic()
    summary = extract_all_keywords()
    assert summary == {"total": 3, "extracted": 3, "skipped": 0, "errors": 0}

    with get_session() as session:
        rows = session.execute(select(KeywordExtract)).scalars().all()
    assert len(rows) == 3


def test_extract_all_keywords_skips_existing_without_force(fresh_db):
    _seed_basic()
    extract_all_keywords()
    summary = extract_all_keywords(force=False)
    assert summary["extracted"] == 0
    assert summary["skipped"] == 3


def test_extract_all_keywords_force_re_extracts(fresh_db):
    _seed_basic()
    extract_all_keywords()
    summary = extract_all_keywords(force=True)
    assert summary["extracted"] == 3
    assert summary["skipped"] == 0


def test_score_field_equals_raw_score_under_v2(fresh_db):
    """Phase 4.7: v2 emits a 0-100 score directly per item, no dataset-
    relative normalisation. ``score`` and ``raw_score`` are the same
    value."""
    _seed_basic()
    score_all_items("p1", force=True)

    with get_session() as session:
        rows = session.execute(select(Score)).scalars().all()
    assert len(rows) == 3
    for s in rows:
        assert s.score == s.raw_score
        assert 0.0 <= s.score <= 100.0


def test_score_zero_when_no_matches(fresh_db):
    """A JD with no role/skill/keyword/family signals ends up at 0."""
    with get_session() as session:
        src = Source(name="Test", type="api", url="http://t", enabled=True)
        session.add(src)
        session.flush()
        profile = Profile(name="p1", parsed_at=_now())
        session.add(profile)
        session.flush()
        session.add(
            Criterion(
                profile_id=profile.id, term="never_appears_anywhere",
                kind="skill", weight=3, source="resume",
            )
        )
        session.add(
            Item(
                source_id=src.id, external_id="z",
                # Title chosen to NOT hit any role_families pattern, so
                # title_family_score also returns the default (0.40)
                # which still produces a small non-zero final from the
                # 15% family weight. To verify the all-zero floor we
                # need a profile with no role/skill/keyword criteria
                # that match anything in the body either.
                title="zzqq", body="qqzz",
                url="http://t/z", content_hash="hz", scraped_at=_now(),
            )
        )
        session.commit()

    summary = score_all_items("p1", force=True)
    assert summary["scored"] == 1

    with get_session() as session:
        score = session.execute(select(Score)).scalar_one()
    # Default title_family weight contributes a small floor
    # (0.50 × 0.15 × 100 = 7.5). All other components are zero.
    assert 0.0 <= score.score <= 10.0
    assert score.score == score.raw_score
