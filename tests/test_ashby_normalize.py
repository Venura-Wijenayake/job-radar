from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from scrapers.ashby import ASHBY_DISPLAY_NAMES, AshbyScraper


SAMPLE_RAW = {
    "id": "abc123",
    "title": "Senior Data Analyst",
    "descriptionHtml": (
        "&lt;p&gt;We're hiring a senior data analyst to drive our reporting "
        "stack in San Francisco. Strong SQL, Python, and dbt skills "
        "expected.&lt;/p&gt;"
    ),
    "jobUrl": "https://jobs.ashbyhq.com/anthropic/abc123",
    "applyUrl": "https://jobs.ashbyhq.com/anthropic/abc123/apply",
    "publishedAt": "2026-04-15T10:30:00.000Z",
    "location": "San Francisco, CA",
    "team": "Data",
    "employmentType": "FullTime",
    "compensation": {
        "compensationTierSummary": "$140k–$180k",
    },
    "__slug__": "anthropic",
}


def _make_scraper() -> AshbyScraper:
    return AshbyScraper(slugs=[], sleep_between=0)


def test_normalize_maps_top_level_fields():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "ashby_anthropic_abc123"
    assert norm["title"] == "Senior Data Analyst"
    assert norm["url"] == "https://jobs.ashbyhq.com/anthropic/abc123"
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2026


def test_normalize_extracts_location_string():
    md = _make_scraper().normalize(SAMPLE_RAW)["metadata_json"]
    assert md["location"] == "San Francisco, CA"
    # location_normalized routed through normalize_location → "US"
    assert md["location_normalized"] == "US"


def test_normalize_unescapes_html_entities_in_body():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    body = norm["body"]
    # &lt;p&gt; → <p> → stripped → plain text
    assert "<p>" not in body
    assert "&lt;" not in body
    assert "senior data analyst" in body.lower()


def test_normalize_prefers_descriptionPlain_when_present():
    raw = dict(SAMPLE_RAW)
    raw["descriptionPlain"] = "Already plain text body."
    norm = _make_scraper().normalize(raw)
    assert norm["body"] == "Already plain text body."


def test_normalize_handles_missing_compensation():
    raw = dict(SAMPLE_RAW)
    raw.pop("compensation", None)
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    md = norm["metadata_json"]
    assert md.get("salary_min") is None
    assert md.get("salary_max") is None


def test_normalize_uses_display_name_dict_for_company():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm["metadata_json"]["company"] == "Anthropic"


def test_normalize_uses_titlecase_fallback_for_unknown_slug():
    raw = dict(SAMPLE_RAW)
    raw["__slug__"] = "newco"
    raw["id"] = "z9"
    norm = _make_scraper().normalize(raw)
    assert norm["external_id"] == "ashby_newco_z9"
    assert norm["metadata_json"]["company"] == "Newco"


def test_normalize_packs_eligibility_metadata():
    md = _make_scraper().normalize(SAMPLE_RAW)["metadata_json"]
    assert "citizenship_required" in md
    assert "license_required" in md
    assert "ghost_score" in md
    assert "geo_tier" in md
    assert "language_detected" in md
    assert md["search_term"] == "direct_board"


def test_normalize_skips_missing_required_fields():
    s = _make_scraper()
    assert s.normalize({}) is None
    assert s.normalize({"id": "x"}) is None
    assert s.normalize({"title": "T"}) is None


def _stub_response(payload, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _stub_404():
    resp = MagicMock()
    resp.status_code = 404
    err = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=resp
    )
    resp.raise_for_status = MagicMock(side_effect=err)
    return resp


def test_fetch_skips_404_slugs(monkeypatch):
    payloads = iter([
        _stub_response({"jobs": [{"id": "1", "title": "Eng"}]}),
        _stub_404(),
        _stub_response({"jobs": [{"id": "2", "title": "PM"}]}),
    ])

    def fake_get(url, headers=None, timeout=None):
        return next(payloads)

    monkeypatch.setattr(httpx, "get", fake_get)

    s = AshbyScraper(slugs=["good-1", "missing", "good-2"], sleep_between=0)
    items = s.fetch()
    assert len(items) == 2
    assert s._slugs_attempted == 3
    assert s._slugs_with_jobs == 2
    assert any(slug == "missing" for slug, _ in s._failed_slugs)


def test_display_names_dict_covers_known_slugs():
    """Spot-check the dict has the highest-priority AI labs."""
    assert ASHBY_DISPLAY_NAMES["anthropic"] == "Anthropic"
    assert ASHBY_DISPLAY_NAMES["openai"] == "OpenAI"
    assert ASHBY_DISPLAY_NAMES["characterai"] == "Character.AI"
    assert ASHBY_DISPLAY_NAMES["weights-and-biases"] == "Weights & Biases"
