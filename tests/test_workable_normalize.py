from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from scrapers.workable import WorkableScraper


SAMPLE_RAW = {
    "id": "ABC123XYZ",
    "shortcode": "DEF456",
    "title": "Junior Data Analyst",
    "description": (
        "&lt;p&gt;Join our growing analytics team. We work with python, "
        "sql, and tableau every day.&lt;/p&gt;"
    ),
    "requirements": "&lt;ul&gt;&lt;li&gt;1+ years SQL&lt;/li&gt;&lt;/ul&gt;",
    "benefits": "&lt;p&gt;Equity + remote work.&lt;/p&gt;",
    "location": {
        "city": "San Francisco",
        "region": "California",
        "country": "United States",
        "countryCode": "US",
        "workplace": "hybrid",
    },
    "department": "Analytics",
    "employment_type": "full-time",
    "published": "2026-04-15T10:30:00.000Z",
    "shortlink": "https://apply.workable.com/acme/j/ABC123XYZ",
    "application_url": "https://apply.workable.com/acme/j/ABC123XYZ/apply",
    "__slug__": "acme",
    "__company_name__": "Acme",
}


def _make_scraper() -> WorkableScraper:
    return WorkableScraper(slugs=[], sleep_between=0)


def test_normalize_maps_top_level_fields():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "workable_acme_ABC123XYZ"
    assert norm["title"] == "Junior Data Analyst"
    # application_url preferred over shortlink
    assert norm["url"].endswith("/apply")
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2026


def test_normalize_concatenates_description_requirements_benefits():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    body = norm["body"]
    # description content
    assert "analytics team" in body.lower()
    # requirements content
    assert "1+ years sql" in body.lower()
    # benefits content
    assert "equity" in body.lower()


def test_normalize_unescapes_html_entities_in_body():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    body = norm["body"]
    # &lt;p&gt; → <p> → stripped → plain text
    assert "<p>" not in body
    assert "&lt;" not in body


def test_normalize_builds_location_string_from_structured_fields():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    md = norm["metadata_json"]
    assert md["location"] == "San Francisco, California, United States"
    # Routed through normalize_location → "US" bucket
    assert md["location_normalized"] == "US"


def test_normalize_detects_remote_workplace():
    raw = dict(SAMPLE_RAW)
    raw["location"] = {
        "city": "",
        "region": "",
        "country": "",
        "workplace": "remote",
    }
    norm = _make_scraper().normalize(raw)
    md = norm["metadata_json"]
    assert "Remote" in (md["location"] or "")
    assert md["workplace"] == "remote"


def test_normalize_handles_missing_optional_fields():
    """Missing description/requirements/benefits/location/department all
    survive normalisation — body becomes empty string, location None."""
    minimal = {
        "id": "z9",
        "title": "Engineer",
        "__slug__": "newco",
    }
    norm = _make_scraper().normalize(minimal)
    assert norm is not None
    assert norm["external_id"] == "workable_newco_z9"
    assert norm["body"] == ""
    md = norm["metadata_json"]
    assert md["location"] is None
    assert md["department"] is None


def test_normalize_uses_company_name_when_present():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm["metadata_json"]["company"] == "Acme"


def test_normalize_falls_back_to_titlecase_slug_when_company_missing():
    raw = dict(SAMPLE_RAW)
    raw.pop("__company_name__")
    norm = _make_scraper().normalize(raw)
    assert norm["metadata_json"]["company"] == "Acme"  # slug.title()


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


def _stub_response(payload):
    resp = MagicMock()
    resp.status_code = 200
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
        _stub_response({
            "account": {"name": "Good One"},
            "jobs": [{"id": "1", "title": "Eng"}],
        }),
        _stub_404(),
        _stub_response({
            "account": {"name": "Good Two"},
            "jobs": [{"id": "2", "title": "PM"}],
        }),
    ])

    def fake_get(url, headers=None, timeout=None):
        return next(payloads)

    monkeypatch.setattr(httpx, "get", fake_get)

    s = WorkableScraper(slugs=["good-1", "missing", "good-2"], sleep_between=0)
    items = s.fetch()
    assert len(items) == 2
    assert s._slugs_attempted == 3
    assert s._slugs_with_jobs == 2
    assert any(slug == "missing" for slug, _ in s._failed_slugs)
    # Company name from account-level field is grafted onto each job
    assert items[0]["__company_name__"] == "Good One"
    assert items[1]["__company_name__"] == "Good Two"
