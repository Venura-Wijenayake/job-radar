"""Phase 4.7 — match_score_v2 sub-component coverage."""
from __future__ import annotations

from scoring.match_score_v2 import (
    MATCH_TITLE_FAMILY_WEIGHTS,
    TARGET_SKILL_DENSITY,
    TARGET_SKILL_POINTS,
    W_FAMILY,
    W_KEYWORD,
    W_ROLE,
    W_SKILL,
    body_keyword_score,
    compute_match_score,
    matched_terms_from_breakdown,
    role_match_score,
    role_match_score_with_body,
    skill_match_score,
    title_family_score,
)


# ----- families fixture -----


def _families():
    return {
        "families": [
            {
                "name": "data_analyst_exact",
                "patterns": ["data analyst", "junior data analyst"],
                "multiplier": 1.0,
            },
            {
                "name": "data_analyst_adjacent",
                "patterns": ["business analyst", "data scientist"],
                "multiplier": 0.97,
            },
            {
                "name": "operations_quant_research_analyst",
                "patterns": ["operations analyst", "risk analyst"],
                "multiplier": 0.95,
            },
            {
                "name": "junior_dev",
                "patterns": ["junior software engineer"],
                "multiplier": 0.95,
            },
            {
                "name": "qa_tester",
                "patterns": ["qa analyst"],
                "multiplier": 0.95,
            },
            {
                "name": "it_support_pivot",
                "patterns": ["it support", "help desk"],
                "multiplier": 0.90,
            },
        ],
        "default_multiplier": 0.85,
    }


# ----- role_match_score -----


def test_role_match_exact_returns_1_0():
    assert role_match_score("Data Analyst", ["data analyst"]) == 1.0


def test_role_match_in_senior_title_still_1_0():
    """Word-boundary substring: 'Senior Data Analyst' matches the role."""
    assert role_match_score("Senior Data Analyst", ["data analyst"]) == 1.0


def test_role_match_no_role_in_title_returns_0():
    assert role_match_score("Plumber", ["data analyst"]) == 0.0


def test_role_match_empty_title_returns_0():
    assert role_match_score("", ["data analyst"]) == 0.0
    assert role_match_score(None, ["data analyst"]) == 0.0


def test_role_match_with_body_falls_back_to_0_5():
    """Role in body but not title → 0.5."""
    score = role_match_score_with_body(
        "Engineer", "Looking for a data analyst", ["data analyst"]
    )
    assert score == 0.5


def test_role_match_with_body_title_still_wins():
    score = role_match_score_with_body(
        "Data Analyst", "Looking for a data analyst", ["data analyst"]
    )
    assert score == 1.0


def test_role_match_with_body_no_match_returns_0():
    score = role_match_score_with_body(
        "Engineer", "Hiring a developer", ["data analyst"]
    )
    assert score == 0.0


# ----- skill_match_score -----


def test_skill_match_zero_when_empty_body():
    score, matched = skill_match_score("", [{"term": "python", "weight_tier": 1}])
    assert score == 0.0
    assert matched == []


def test_skill_match_zero_when_no_criteria():
    score, matched = skill_match_score("Python everywhere", [])
    assert score == 0.0
    assert matched == []


def test_skill_match_8_skills_normalizes_to_1_0():
    """8 mid-tier (weight 2) skills = 16 points = TARGET_SKILL_POINTS → 1.0."""
    crits = [{"term": f"s{i}", "weight_tier": 2} for i in range(8)]
    body = " ".join(f"s{i}" for i in range(8))
    score, matched = skill_match_score(body, crits)
    assert score == 1.0
    assert len(matched) == 8


def test_skill_match_4_skills_returns_0_5():
    """4 mid-tier matches = 8 points / 16 target = 0.5."""
    crits = [{"term": f"s{i}", "weight_tier": 2} for i in range(8)]
    body = "s0 s1 s2 s3"
    score, _ = skill_match_score(body, crits)
    assert score == 0.5


def test_skill_match_tier_1_weights_more_than_tier_3():
    """One tier-1 hit (3 points) > three tier-3 hits (3 points combined,
    same value); but 2 tier-1 hits (6) > 4 tier-3 hits (4)."""
    crits_t1 = [{"term": "py", "weight_tier": 1}, {"term": "sql", "weight_tier": 1}]
    crits_t3 = [
        {"term": "a", "weight_tier": 3},
        {"term": "b", "weight_tier": 3},
        {"term": "c", "weight_tier": 3},
        {"term": "d", "weight_tier": 3},
    ]
    score_t1, _ = skill_match_score("py sql", crits_t1)
    score_t3, _ = skill_match_score("a b c d", crits_t3)
    assert score_t1 > score_t3


def test_skill_match_returns_matched_terms_list():
    crits = [
        {"term": "python", "weight_tier": 1},
        {"term": "tableau", "weight_tier": 2},
        {"term": "kubernetes", "weight_tier": 3},
    ]
    body = "We use python and kubernetes; not tableau."
    _, matched = skill_match_score(body, crits)
    # All three appear (tableau as substring of "tableau" too — not the
    # opposite). Verify both python and kubernetes are present.
    assert "python" in matched
    assert "kubernetes" in matched
    assert "tableau" in matched  # appears in "not tableau" body


def test_skill_match_caps_at_1_0_with_excess():
    """Hitting 12 mid-tier skills (24 points) caps at 1.0, not 1.5."""
    crits = [{"term": f"s{i}", "weight_tier": 2} for i in range(12)]
    body = " ".join(f"s{i}" for i in range(12))
    score, _ = skill_match_score(body, crits)
    assert score == 1.0


# ----- title_family_score -----


def test_title_family_score_data_analyst_exact_returns_1_0():
    score, name = title_family_score("Data Analyst", _families())
    assert score == 1.0
    assert name == "data_analyst_exact"


def test_title_family_score_ops_analyst_returns_0_85():
    score, name = title_family_score("Operations Analyst", _families())
    assert score == 0.85
    assert name == "operations_quant_research_analyst"


def test_title_family_score_it_support_returns_0_60():
    score, name = title_family_score("IT Support Specialist", _families())
    assert score == 0.60
    assert name == "it_support_pivot"


def test_title_family_score_default_for_no_match():
    score, name = title_family_score("Hospitality Coordinator", _families())
    assert score == MATCH_TITLE_FAMILY_WEIGHTS["default"]
    assert name == "default"


# ----- body_keyword_score -----


def test_body_keyword_score_zero_when_no_criteria():
    score, matched = body_keyword_score("python", [])
    assert score == 0.0
    assert matched == []


def test_body_keyword_score_full_match_returns_1_0():
    crits = [{"term": "analytics", "kind": "keyword"}]
    score, matched = body_keyword_score("We use analytics.", crits)
    assert score == 1.0
    assert matched == ["analytics"]


def test_body_keyword_score_partial_match_normalises():
    crits = [
        {"term": "analytics"},
        {"term": "automation"},
        {"term": "documentation"},
    ]
    score, matched = body_keyword_score(
        "Strong analytics and documentation skills.", crits
    )
    # 2 of 3 → 0.667
    assert abs(score - (2 / 3)) < 0.01
    assert "analytics" in matched
    assert "documentation" in matched


# ----- compute_match_score -----


def _profile():
    return [
        {"term": "data analyst", "kind": "role", "weight_tier": 2},
        {"term": "python", "kind": "skill", "weight_tier": 1},
        {"term": "sql", "kind": "skill", "weight_tier": 1},
        {"term": "excel", "kind": "skill", "weight_tier": 1},
        {"term": "analytics", "kind": "keyword", "weight_tier": 2},
    ]


def test_compute_match_score_combines_components():
    item = {
        "title": "Data Analyst",
        "body": "We use python, sql, excel daily for analytics.",
    }
    score, breakdown = compute_match_score(item, _profile(), _families())
    # Role 1.0 × 0.30 = 0.30
    # Skill: 3 tier-1 hits = 9 points / 16 = 0.5625; × 0.45 = 0.253
    # Family data_analyst_exact 1.0 × 0.15 = 0.15
    # Keyword 1/1 = 1.0 × 0.10 = 0.10
    # Total ≈ 80.3
    assert abs(score - 80.3) < 0.5
    assert breakdown["role_match_score"] == 1.0
    assert "python" in breakdown["matched_skills"]
    assert breakdown["title_family_matched"] == "data_analyst_exact"


def test_compute_match_score_capped_at_100():
    """A perfect-fit item shouldn't exceed 100."""
    crits = [{"term": "data analyst", "kind": "role"}] + [
        {"term": f"s{i}", "kind": "skill", "weight_tier": 1} for i in range(20)
    ]
    item = {
        "title": "Data Analyst",
        "body": " ".join(f"s{i}" for i in range(20))
        + " analytics automation documentation",
    }
    score, _ = compute_match_score(item, crits, _families())
    assert score <= 100.0


def test_compute_match_score_returns_breakdown_dict():
    item = {"title": "Data Analyst", "body": "python"}
    score, breakdown = compute_match_score(item, _profile(), _families())
    for key in (
        "role_match_score",
        "skill_match_score",
        "title_family_score",
        "title_family_matched",
        "body_keyword_score",
        "matched_skills",
        "matched_keywords",
        "weights",
        "final",
    ):
        assert key in breakdown
    assert breakdown["final"] == score


def test_compute_match_score_zero_when_no_signals():
    """Plumber title, plumbing body, no role/skill/keyword matches —
    only the default family floor (0.50 × 0.15 × 100 = 7.5) contributes."""
    item = {"title": "Plumber", "body": "Fixing pipes and water heaters."}
    score, breakdown = compute_match_score(item, _profile(), _families())
    assert breakdown["role_match_score"] == 0.0
    assert breakdown["skill_match_score"] == 0.0
    assert breakdown["title_family_matched"] == "default"
    assert breakdown["body_keyword_score"] == 0.0
    assert score == 7.5  # 0.50 × 0.15 × 100


def test_weights_sum_to_1():
    assert abs((W_ROLE + W_SKILL + W_FAMILY + W_KEYWORD) - 1.0) < 1e-9


# ----- integration: ashby AI-lab JD -----


def test_ashby_ai_lab_jd_with_skills_scores_above_50():
    """Synthetic JD mimicking an OpenAI Risk Analyst posting: title is
    'Risk Analyst' (operations_quant_research_analyst family, 0.85)
    and body mentions python, sql, analytics, automation, jupyter."""
    crits = [
        {"term": "data analyst", "kind": "role", "weight_tier": 2},
        {"term": "python", "kind": "skill", "weight_tier": 1},
        {"term": "sql", "kind": "skill", "weight_tier": 1},
        {"term": "excel", "kind": "skill", "weight_tier": 1},
        {"term": "git", "kind": "skill", "weight_tier": 1},
        {"term": "jupyter", "kind": "skill", "weight_tier": 1},
        {"term": "pandas", "kind": "skill", "weight_tier": 1},
        {"term": "analytics", "kind": "keyword"},
    ]
    item = {
        "title": "Risk Analyst",
        "body": (
            "We use python, sql, jupyter, pandas, git, and excel "
            "for analytics and risk modelling."
        ),
    }
    score, _ = compute_match_score(item, crits, _families())
    assert score > 50.0, f"Ashby AI-lab JD scored only {score}"


# ----- matched_terms_from_breakdown shape -----


def test_matched_terms_reshaping_v1_compat():
    """The dashboard's top_matched_terms field consumes
    {term, kind, contribution} dicts. Ensure the v2-to-v1 reshaping
    produces those keys."""
    item = {"title": "Data Analyst", "body": "python sql analytics"}
    _, breakdown = compute_match_score(item, _profile(), _families())
    matched = matched_terms_from_breakdown(breakdown)
    for entry in matched:
        assert "term" in entry
        assert "kind" in entry
        assert "contribution" in entry
