from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from scrapers.greenhouse import GreenhouseScraper

SAMPLE_RAW = {
    "id": 4123456,
    "title": "Senior Data Analyst",
    "content": (
        "&lt;p&gt;We're hiring a senior data analyst to drive our reporting "
        "stack in San Francisco. Strong SQL, Python, and dbt skills "
        "expected.&lt;/p&gt;&lt;p&gt;Visit our careers page for more.&lt;/p&gt;"
    ),
    "absolute_url": "https://boards.greenhouse.io/acme/jobs/4123456",
    "updated_at": "2026-04-15T10:30:00Z",
    "location": {"name": "San Francisco, CA"},
    "departments": [
        {"id": 1, "name": "Data"},
        {"id": 2, "name": "Analytics"},
    ],
    "offices": [{"id": 10, "name": "San Francisco HQ"}],
    "metadata": [],
    "__slug__": "acme",
}


def _make_scraper() -> GreenhouseScraper:
    return GreenhouseScraper(slugs=[], sleep_between=0)


def test_normalize_maps_top_level_fields():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "gh_acme_4123456"
    assert norm["title"] == "Senior Data Analyst"
    assert norm["url"] == "https://boards.greenhouse.io/acme/jobs/4123456"
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2026


def test_normalize_decodes_html_body():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    body = norm["body"]
    # Tags should be stripped after HTML cleaning
    assert "<p>" not in body
    assert "senior data analyst" in body.lower()


def test_normalize_packs_metadata():
    md = _make_scraper().normalize(SAMPLE_RAW)["metadata_json"]
    assert md["company"] == "acme"
    assert md["slug"] == "acme"
    assert md["location"] == "San Francisco, CA"
    assert md["departments"] == ["Data", "Analytics"]
    assert md["offices"] == ["San Francisco HQ"]
    assert "citizenship_required" in md
    assert "license_required" in md
    assert "ghost_score" in md
    assert "location_normalized" in md
    assert "language_detected" in md
    assert "geo_tier" in md


def test_normalize_handles_missing_location():
    raw = dict(SAMPLE_RAW)
    raw.pop("location", None)
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    assert norm["metadata_json"]["location"] is None


def test_normalize_handles_empty_departments():
    raw = dict(SAMPLE_RAW)
    raw["departments"] = []
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    assert norm["metadata_json"]["departments"] == []


def test_normalize_skips_missing_required_fields():
    s = _make_scraper()
    assert s.normalize({}) is None
    assert s.normalize({"id": 1}) is None
    assert s.normalize({"title": "T"}) is None


def test_normalize_iso_with_z_suffix():
    raw = dict(SAMPLE_RAW)
    raw["updated_at"] = "2026-01-02T03:04:05Z"
    norm = _make_scraper().normalize(raw)
    assert norm["posted_at"].year == 2026
    assert norm["posted_at"].month == 1


def test_normalize_handles_invalid_date():
    raw = dict(SAMPLE_RAW)
    raw["updated_at"] = "not-a-date"
    raw.pop("first_published", None)
    norm = _make_scraper().normalize(raw)
    assert norm["posted_at"] is None


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
        _stub_response({"jobs": [{"id": 1, "title": "Eng"}]}),
        _stub_404(),
        _stub_response({"jobs": [{"id": 2, "title": "PM"}]}),
    ])

    def fake_get(url, headers=None, timeout=None):
        return next(payloads)

    monkeypatch.setattr(httpx, "get", fake_get)

    s = GreenhouseScraper(
        slugs=["good-1", "missing", "good-2"],
        sleep_between=0,
    )
    items = s.fetch()
    assert len(items) == 2
    assert s._slugs_attempted == 3
    assert s._slugs_with_jobs == 2
    assert any(slug == "missing" for slug, _ in s._failed_slugs)
