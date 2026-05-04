from __future__ import annotations

from scoring.fit_tier import classify_fit_tier, count_yellow_flags


def _item(title="", body="", score=70.0):
    return {"title": title, "body": body, "score": score}


# ----- count_yellow_flags -----


def test_count_no_flags_for_plain_title():
    assert count_yellow_flags("Data Analyst", "We are hiring.") == 0


def test_count_one_flag_for_senior_title():
    assert count_yellow_flags("Senior Data Analyst", "") == 1


def test_count_two_flags_for_senior_staff_title():
    assert count_yellow_flags("Senior Staff Data Analyst", "") == 2


def test_count_caps_at_three():
    """A pathological 5-flag input must still cap at 3."""
    title = "Senior Staff Principal Lead Director Data Analyst II"
    body = "10+ years experience required"
    assert count_yellow_flags(title, body) == 3


def test_count_lead_word_boundary_match():
    assert count_yellow_flags("Lead Data Analyst", "") == 1


def test_count_lead_does_not_match_leadership():
    """Word boundary: 'leadership' shouldn't trigger the 'lead' flag."""
    assert (
        count_yellow_flags(
            "Data Analyst",
            "great leadership opportunities in this role",
        )
        == 0
    )


def test_count_roman_numeral_two():
    assert count_yellow_flags("Data Analyst II", "") == 1


def test_count_roman_numeral_three_and_four():
    assert count_yellow_flags("Data Analyst III", "") == 1
    assert count_yellow_flags("Engineer IV", "") == 1


def test_count_no_numeral_when_absent():
    assert count_yellow_flags("Data Analyst", "") == 0


def test_count_body_experience_5plus_years():
    assert count_yellow_flags("Data Analyst", "5+ years experience") >= 1


def test_count_body_experience_10plus_years():
    assert count_yellow_flags("Data Analyst", "10+ years required") >= 1


def test_count_body_minimum_5_years():
    assert count_yellow_flags("Data Analyst", "minimum 5 years in industry") >= 1


def test_count_handles_empty_strings():
    assert count_yellow_flags("", "") == 0


def test_count_handles_none():
    assert count_yellow_flags(None, None) == 0


def test_junior_overrides_seniority_term_in_title():
    """'Junior' in the title suppresses the title-seniority count.
    'Junior to Mid-Senior Analyst' — the junior wins."""
    assert count_yellow_flags("Junior to Mid-Senior Analyst", "") == 0
    assert count_yellow_flags("Junior Senior Engineer", "") == 0


def test_junior_does_not_suppress_numerals():
    """A 'Junior Data Analyst II' still has the level-II flag — the
    numeric level is a real signal regardless of the junior tag."""
    assert count_yellow_flags("Junior Data Analyst II", "") == 1


def test_junior_does_not_suppress_body_experience():
    """A junior-titled role asking for 10+ years is contradictory but
    the body signal still counts as a flag."""
    assert (
        count_yellow_flags("Junior Data Analyst", "10+ years experience")
        >= 1
    )


# ----- classify_fit_tier -----


def test_high_fit_score_85_clean_title():
    assert classify_fit_tier(_item("Data Analyst", "", 85.0)) == "high_fit"


def test_high_fit_score_exactly_80_no_flags():
    assert classify_fit_tier(_item("Data Analyst", "", 80.0)) == "high_fit"


def test_stretch_score_79_no_flags():
    """Below the 80 cutoff falls to stretch even with zero flags."""
    assert classify_fit_tier(_item("Data Analyst", "", 79.0)) == "stretch"


def test_stretch_score_85_one_yellow_flag():
    assert classify_fit_tier(_item("Senior Data Analyst", "", 85.0)) == "stretch"


def test_long_shot_low_score():
    assert classify_fit_tier(_item("Data Analyst", "", 30.0)) == "long_shot"


def test_long_shot_score_just_below_cutoff():
    assert classify_fit_tier(_item("Data Analyst", "", 49.9)) == "long_shot"


def test_long_shot_multiple_flags_with_decent_score():
    """Senior + Staff in title + 10+ years in body = 3 flags. Score 75
    still drops to long_shot when flags >= 2."""
    item = _item("Senior Staff Data Analyst", "10+ years required", 75.0)
    assert classify_fit_tier(item) == "long_shot"


def test_long_shot_high_score_with_two_flags():
    """Even a 90 score drops to long_shot when 2+ flags are present."""
    item = _item("Senior Staff Data Analyst", "", 90.0)
    assert classify_fit_tier(item) == "long_shot"


def test_junior_data_analyst_high_score_is_high_fit():
    """The bug fix: 'Junior Data Analyst' must NOT be flagged seniority
    via 'senior' regex spillover or other mishap."""
    assert classify_fit_tier(_item("Junior Data Analyst", "", 85.0)) == "high_fit"


def test_lead_engineer_one_flag_at_high_score_is_stretch():
    assert classify_fit_tier(_item("Lead Engineer", "", 85.0)) == "stretch"


def test_leadership_opportunities_in_body_does_not_drop_high_fit():
    """Regression: 'leadership' in body shouldn't trigger the 'lead' flag."""
    item = _item(
        "Data Analyst",
        "Great leadership opportunities in this role.",
        85.0,
    )
    assert classify_fit_tier(item) == "high_fit"


def test_handles_none_body():
    item = {"title": "Data Analyst", "body": None, "score": 85.0}
    assert classify_fit_tier(item) == "high_fit"


def test_handles_missing_score():
    """Missing score falls back to 0 → long_shot."""
    item = {"title": "Data Analyst", "body": ""}
    assert classify_fit_tier(item) == "long_shot"
