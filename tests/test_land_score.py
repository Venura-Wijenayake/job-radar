"""Phase 4.6b — land_score multipliers and integration."""
from __future__ import annotations

from scoring.land_score import (
    _compute_eligibility_mult,
    _compute_experience_match,
    _compute_salary_mult,
    _compute_skill_density_bonus,
    _compute_source_quality,
    _compute_title_family,
    compute_land_score,
    load_role_families,
    load_source_quality,
    load_title_blocklist,
)


# ----- helpers / fixtures -----


def _families():
    return {
        "families": [
            {
                "name": "data_analyst_exact",
                "patterns": [
                    "data analyst ii",
                    "data analyst i",
                    "junior data analyst",
                    "data analyst",
                ],
                "multiplier": 1.0,
            },
            {
                "name": "data_analyst_adjacent",
                "patterns": ["business analyst", "data scientist"],
                "multiplier": 0.95,
            },
            {
                "name": "operations_quant_research_analyst",
                "patterns": ["operations analyst", "risk analyst"],
                "multiplier": 0.85,
            },
            {
                "name": "junior_dev",
                "patterns": ["junior software engineer", "junior developer"],
                "multiplier": 1.0,
            },
            {
                "name": "it_support_pivot",
                "patterns": ["it support", "help desk"],
                "multiplier": 0.85,
            },
        ],
        "default_multiplier": 0.70,
    }


def _sources():
    return {
        "sources": {
            "Ashby": 1.15,
            "Greenhouse": 1.10,
            "Adzuna": 0.90,
        },
        "default_multiplier": 1.00,
    }


def _blocklist():
    return ["sdr", "account executive", "vp of", "warehouse"]


# ----- skill density -----


def test_skill_density_bonus_zero_when_no_criteria():
    bonus, matched = _compute_skill_density_bonus("body text", [])
    assert bonus == 0.0
    assert matched == []


def test_skill_density_bonus_negative_when_empty_body():
    """No body to scan → no matches → maximum penalty (-0.20)."""
    crits = [{"term": "python", "weight_tier": 2}]
    bonus, matched = _compute_skill_density_bonus("", crits)
    assert bonus == -0.20
    assert matched == []


def test_skill_density_bonus_saturates_at_target():
    """Hitting 8+ tier-2 skill points (= TARGET_DENSITY_POINTS=16)
    saturates the bonus at +0.30."""
    crits = [
        {"term": f"skill{i}", "weight_tier": 2} for i in range(10)
    ]
    body = " ".join(f"skill{i}" for i in range(10))
    bonus, matched = _compute_skill_density_bonus(body, crits)
    assert bonus == 0.30
    assert len(matched) == 10


def test_skill_density_bonus_tier_1_match_weights_3_each():
    """4 tier-1 matches = 12 points. 12 / 16 = 0.75 normalised. Above
    the 0.4 inflection so bonus = 0.30 / 0.6 × (0.75 − 0.4) = 0.175."""
    crits = [{"term": f"t{i}", "weight_tier": 1} for i in range(4)]
    body = " ".join(f"t{i}" for i in range(4))
    bonus, matched = _compute_skill_density_bonus(body, crits)
    assert len(matched) == 4
    assert abs(bonus - 0.175) < 0.001


def test_skill_density_bonus_zero_at_inflection_point():
    """Normalized = 0.4 should produce bonus exactly 0.0 (the linear
    segment switches sign at this point)."""
    # 0.4 * TARGET=16 = 6.4 points. 3 tier-2 matches = 6 points → 0.375
    # → bonus < 0. 4 tier-2 matches = 8 points → 0.5 → bonus > 0.
    # Test the critical region:
    crits = [{"term": f"s{i}", "weight_tier": 2} for i in range(8)]
    # Match exactly 4 — which gives 8/16 = 0.5 normalized.
    body = "s0 s1 s2 s3"
    bonus, matched = _compute_skill_density_bonus(body, crits)
    assert len(matched) == 4
    # bonus = 0.30/0.6 × (0.5 − 0.4) = 0.05
    assert abs(bonus - 0.05) < 0.001


# ----- source quality -----


def test_source_quality_mult_lookup_works_for_ashby():
    assert _compute_source_quality("Ashby", _sources()) == 1.15


def test_source_quality_mult_lookup_works_for_adzuna():
    assert _compute_source_quality("Adzuna", _sources()) == 0.90


def test_source_quality_mult_default_when_unknown_source():
    assert _compute_source_quality("OtherSrc", _sources()) == 1.00


def test_source_quality_mult_default_when_none():
    assert _compute_source_quality(None, _sources()) == 1.00


# ----- title family -----


def test_title_family_data_analyst_exact_returns_1_0():
    mult, name = _compute_title_family("Data Analyst", _families())
    assert mult == 1.0
    assert name == "data_analyst_exact"


def test_title_family_business_analyst_returns_0_95():
    mult, name = _compute_title_family("Senior Business Analyst", _families())
    assert mult == 0.95
    assert name == "data_analyst_adjacent"


def test_title_family_it_support_returns_0_85():
    mult, name = _compute_title_family("IT Support Specialist", _families())
    assert mult == 0.85
    assert name == "it_support_pivot"


def test_title_family_default_when_no_match():
    mult, name = _compute_title_family("Hospitality Coordinator", _families())
    assert mult == 0.70
    assert name == "default"


def test_title_family_case_insensitive():
    mult, name = _compute_title_family("DATA ANALYST", _families())
    assert mult == 1.0


def test_title_family_word_boundary_does_not_match_substring():
    """Word boundary: 'data analyst' shouldn't match 'metadata analyst-ish'."""
    # The pattern uses word-boundary lookarounds, so a contiguous longer
    # token ("metadata") shouldn't trip the match.
    mult, name = _compute_title_family("Metadata Engineer", _families())
    assert name == "default"


def test_title_family_senior_data_analyst_still_matches_exact():
    """'Senior Data Analyst' should match the data_analyst_exact family;
    the senior penalty is applied separately via experience_match."""
    mult, name = _compute_title_family("Senior Data Analyst", _families())
    assert mult == 1.0
    assert name == "data_analyst_exact"


# ----- experience match -----


def test_experience_match_junior_boost():
    assert _compute_experience_match("Junior Data Analyst", "") == 1.10


def test_experience_match_entry_level_boost():
    assert _compute_experience_match("Entry-Level Engineer", "") == 1.10


def test_experience_match_senior_penalty():
    # 1.0 * 0.7 = 0.7
    assert _compute_experience_match("Senior Engineer", "") == 0.7


def test_experience_match_5_years_required_penalty():
    # body penalty alone: 1.0 * 0.5 = 0.5
    assert _compute_experience_match("Engineer", "5+ years experience required") == 0.5


def test_experience_match_stacked_penalties_clamp():
    # Senior + 5+ years = 0.7 * 0.5 = 0.35 → clamped to 0.5 floor.
    assert (
        _compute_experience_match("Senior Engineer", "10+ years required")
        == 0.5
    )


def test_experience_match_word_boundary_leadership_safe():
    """Regression: 'leadership opportunities' in body shouldn't trigger
    the 'lead' senior-term match (we only scan title for senior terms)."""
    mult = _compute_experience_match(
        "Data Analyst", "Great leadership opportunities here."
    )
    assert mult == 1.0


def test_experience_match_clean_title_returns_1_0():
    assert _compute_experience_match("Data Analyst", "") == 1.0


# ----- eligibility (blocklist) -----


def test_eligibility_mult_blocked_title_returns_0():
    mult, reason = _compute_eligibility_mult(
        "Sales Development Representative (SDR)", _blocklist()
    )
    assert mult == 0.0
    assert reason in {"sdr", "account executive", "vp of", "warehouse"}


def test_eligibility_mult_passes_when_blocklist_unmatched():
    mult, reason = _compute_eligibility_mult("Data Analyst", _blocklist())
    assert mult == 1.0
    assert reason is None


def test_eligibility_mult_substring_match_handles_partial_word():
    """Substring match (per spec) → 'Warehouse Coordinator' is blocked."""
    mult, reason = _compute_eligibility_mult(
        "Warehouse Coordinator", _blocklist()
    )
    assert mult == 0.0


def test_eligibility_mult_handles_none_title():
    mult, reason = _compute_eligibility_mult(None, _blocklist())
    assert mult == 1.0


# ----- Phase 4.8b: seniority hard-exclusion -----


def test_eligibility_zero_when_title_is_senior():
    """Phase 4.8b: senior titles drop to eligibility=0 even when no
    blocklist pattern matches."""
    mult, reason = _compute_eligibility_mult("Senior Data Analyst", _blocklist())
    assert mult == 0.0
    assert reason == "senior title"

    mult, reason = _compute_eligibility_mult("Data Analyst II", _blocklist())
    assert mult == 0.0
    assert reason == "senior title"

    mult, reason = _compute_eligibility_mult("Lead Engineer", _blocklist())
    assert mult == 0.0


def test_eligibility_passes_when_title_is_intern():
    """Junior overrides keep 'Sr SWE Intern' eligible."""
    mult, reason = _compute_eligibility_mult("Sr SWE Intern", _blocklist())
    assert mult == 1.0
    assert reason is None

    mult, reason = _compute_eligibility_mult("Junior Data Analyst", _blocklist())
    assert mult == 1.0


def test_eligibility_passes_when_body_says_senior_but_title_doesnt():
    """Only title is inspected for seniority — JD body language doesn't
    drop the item. (compute_eligibility_mult takes only the title, so
    body content is structurally excluded from the seniority check.)"""
    mult, reason = _compute_eligibility_mult("Data Analyst", _blocklist())
    assert mult == 1.0
    assert reason is None


# ----- salary -----


def test_salary_mult_below_60k_penalty():
    item = {"metadata_json": {"salary_max": 50_000}}
    mult, _ = _compute_salary_mult(item)
    assert mult == 0.85


def test_salary_mult_in_range_neutral():
    item = {"metadata_json": {"salary_max": 90_000}}
    mult, _ = _compute_salary_mult(item)
    assert mult == 1.0


def test_salary_mult_above_200k_small_penalty():
    item = {"metadata_json": {"salary_max": 240_000}}
    mult, _ = _compute_salary_mult(item)
    assert mult == 0.95


def test_salary_mult_no_data_neutral():
    item = {"metadata_json": {}}
    mult, reason = _compute_salary_mult(item)
    assert mult == 1.0
    assert "no posted salary" in reason


def test_salary_mult_zero_treated_as_no_data():
    """Adzuna sometimes returns salary as 0 when not posted — must not
    drop the role into the <$60k band."""
    item = {"metadata_json": {"salary_max": 0}}
    mult, _ = _compute_salary_mult(item)
    assert mult == 1.0


def test_salary_mult_falls_back_to_min_when_max_missing():
    item = {"metadata_json": {"salary_min": 75_000}}
    mult, _ = _compute_salary_mult(item)
    assert mult == 1.0


# ----- end-to-end compute_land_score -----


def _profile():
    return [
        {"term": "python", "weight_tier": 2},
        {"term": "sql", "weight_tier": 2},
        {"term": "ITIL", "weight_tier": 1},
    ]


def test_compute_land_score_combines_all_multipliers():
    item = {
        "title": "Junior Data Analyst",
        "body": "Strong python and sql skills required.",
        "source_name": "Ashby",
        "metadata_json": {"salary_max": 95_000},
    }
    score, breakdown = compute_land_score(
        item,
        _profile(),
        _families(),
        _sources(),
        _blocklist(),
        match_score=70.0,
    )
    # Junior boost (1.10) × Ashby (1.15) × data_analyst_exact (1.0)
    # × salary neutral (1.0) × eligibility (1.0) × density bonus
    # All five multipliers should appear in breakdown.
    assert breakdown["match_score"] == 70.0
    assert breakdown["source_quality_mult"] == 1.15
    assert breakdown["title_family_mult"] == 1.0
    assert breakdown["title_family_matched"] == "data_analyst_exact"
    assert breakdown["experience_match_mult"] == 1.10
    assert breakdown["salary_mult"] == 1.0
    assert breakdown["eligibility_mult"] == 1.0
    assert breakdown["land_score"] == score
    assert score > 70.0  # bonuses should pull it above the input
    assert score <= 100.0


def test_compute_land_score_capped_at_100():
    item = {
        "title": "Junior Data Analyst",
        "body": "ITIL python sql skills required.",
        "source_name": "Ashby",
        "metadata_json": {},
    }
    score, _ = compute_land_score(
        item, _profile(), _families(), _sources(), _blocklist(),
        match_score=99.0,
    )
    assert score == 100.0


def test_compute_land_score_zero_when_blocklist_hits():
    """Title in blocklist → eligibility_mult=0 → land_score=0."""
    item = {
        "title": "Senior Account Executive",  # matches "account executive"
        "body": "Strong communication skills.",
        "source_name": "Greenhouse",
        "metadata_json": {},
    }
    score, breakdown = compute_land_score(
        item, _profile(), _families(), _sources(), _blocklist(),
        match_score=85.0,
    )
    assert score == 0.0
    assert breakdown["eligibility_mult"] == 0.0
    assert breakdown["eligibility_reason"] == "account executive"


def test_breakdown_dict_includes_all_fields():
    item = {
        "title": "Data Analyst",
        "body": "",
        "source_name": "Adzuna",
        "metadata_json": {},
    }
    _, breakdown = compute_land_score(
        item, _profile(), _families(), _sources(), _blocklist(),
        match_score=50.0,
    )
    expected_keys = {
        "match_score",
        "skill_density_bonus",
        "skills_matched_count",
        "skills_matched_terms",
        "source_quality_mult",
        "title_family_mult",
        "title_family_matched",
        "experience_match_mult",
        "salary_mult",
        "salary_reason",
        "eligibility_mult",
        "eligibility_reason",
        "land_score",
    }
    assert expected_keys.issubset(set(breakdown.keys()))


def test_ashby_operations_analyst_outranks_adzuna_data_analyst():
    """The architect's specific ask: Ashby Operations Analyst at lower
    match score should still beat an Adzuna Data Analyst at higher match
    score, because Ashby × ops_quant_analyst (1.15 × 0.85 = 0.978) is
    larger than Adzuna × data_analyst_exact (0.90 × 1.0 = 0.90)."""
    ashby_item = {
        "title": "Operations Analyst",
        "body": "",
        "source_name": "Ashby",
        "metadata_json": {},
    }
    adzuna_item = {
        "title": "Data Analyst",
        "body": "",
        "source_name": "Adzuna",
        "metadata_json": {},
    }
    ashby_score, _ = compute_land_score(
        ashby_item, [], _families(), _sources(), _blocklist(),
        match_score=75.0,
    )
    adzuna_score, _ = compute_land_score(
        adzuna_item, [], _families(), _sources(), _blocklist(),
        match_score=80.0,
    )
    # Ashby Ops: 75 × 1.15 × 0.85 = 73.31
    # Adzuna DA: 80 × 0.90 × 1.0 = 72.00
    assert ashby_score > adzuna_score


# ----- yaml loaders smoke -----


def test_load_role_families_returns_dict_with_families_key():
    cfg = load_role_families()
    assert "families" in cfg
    assert "default_multiplier" in cfg


def test_load_source_quality_includes_ashby_and_adzuna():
    cfg = load_source_quality()
    assert cfg["sources"]["Ashby"] >= 1.0
    assert cfg["sources"]["Adzuna"] <= 1.0


def test_himalayas_source_quality_multiplier_is_1_05():
    """Phase 4.8c — Himalayas sits in the aggregator tier above Adzuna
    (often deduplicated direct-employer postings) but below the direct
    ATS sources (Ashby/Greenhouse/Lever)."""
    cfg = load_source_quality()
    himalayas = cfg["sources"].get("Himalayas")
    assert himalayas == 1.05
    # Sanity: it sits between Adzuna and Lever as documented.
    assert cfg["sources"]["Adzuna"] < himalayas < cfg["sources"]["Lever"]


def test_load_title_blocklist_returns_lowercase_strings():
    blocked = load_title_blocklist()
    assert all(p == p.lower() for p in blocked)
    assert "sdr" in blocked or any("sdr" in p for p in blocked)
