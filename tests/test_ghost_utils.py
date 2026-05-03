from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scoring.ghost_utils import (
    EXAMPLE_GHOST_JOB,
    EXAMPLE_LEGIT_JOB,
    GHOST_HARD_THRESHOLD,
    GHOST_WARN_THRESHOLD,
    compute_ghost_score,
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_legit_fixture_scores_low():
    score = compute_ghost_score(EXAMPLE_LEGIT_JOB)
    assert score < GHOST_WARN_THRESHOLD


def test_ghost_fixture_scores_high():
    score = compute_ghost_score(EXAMPLE_GHOST_JOB)
    assert score >= GHOST_HARD_THRESHOLD


def test_old_posting_adds_30():
    item = {
        "title": "Data Analyst",
        "body": (
            "We are hiring a data analyst with 2 years of SQL experience. "
            "Visit https://example.com/careers. Plenty of detail. "
            "More sentences. Even more. Final sentence."
        ),
        "posted_at": _now() - timedelta(days=90),
        "salary_min": 70000,
        "salary_max": 90000,
    }
    assert compute_ghost_score(item) >= 30


def test_telegram_contact_adds_30():
    item = {
        "title": "Data Analyst",
        "body": (
            "We are hiring an analyst. Contact via Telegram for details. "
            "Visit https://example.com. Multiple sentences here. "
            "Yet another sentence. Final one."
        ),
        "posted_at": _now(),
    }
    assert compute_ghost_score(item) >= 30


def test_short_body_adds_30():
    item = {
        "title": "Data Analyst",
        "body": "Hiring analyst.",  # under 200 chars
        "posted_at": _now(),
    }
    score = compute_ghost_score(item)
    assert score >= 30


def test_absurd_salary_ratio_adds_15():
    """40k - 300k = 7.5x ratio."""
    long_body = (
        "We're hiring an analyst with great experience. " * 10
        + "Visit https://example.com. Lots of sentences. More. More. Done."
    )
    item = {
        "title": "Data Analyst",
        "body": long_body,
        "posted_at": _now(),
        "salary_min": 40000,
        "salary_max": 300000,
    }
    # Score should include the salary penalty (+15) but not be a hard hit.
    assert compute_ghost_score(item) >= 15


def test_always_hiring_adds_15():
    long_body = (
        "We are always hiring qualified candidates. "
        "Send your resume to careers@example.com. "
        "Visit https://example.com to learn more about our team. "
        "More sentences. Even more. And another. Final."
    )
    item = {
        "title": "Data Analyst",
        "body": long_body,
        "posted_at": _now(),
        "salary_min": 70000,
        "salary_max": 90000,
    }
    assert compute_ghost_score(item) >= 15


def test_red_flag_title_adds_15():
    item = {
        "title": "Earn From Home Data Entry",
        "body": (
            "Easy work for the right candidate. Decent pay. "
            "Visit https://example.com for more. More sentences here. "
            "More. Even more. Done."
        ),
        "posted_at": _now(),
    }
    assert compute_ghost_score(item) >= 15


def test_score_caps_at_100():
    item = {
        "title": "Earn From Home Easy Income",
        "body": "Telegram me. No experience required. High pay. Remote.",
        "posted_at": _now() - timedelta(days=120),
        "salary_min": 30000,
        "salary_max": 400000,
    }
    assert compute_ghost_score(item) <= 100


def test_handles_missing_keys_gracefully():
    """Empty/incomplete dicts should not raise."""
    assert compute_ghost_score({}) >= 0
    assert compute_ghost_score({"title": "x"}) >= 0
