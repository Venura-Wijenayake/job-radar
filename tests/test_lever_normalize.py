from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from scrapers.lever import LeverScraper

SAMPLE_RAW = {
    "id": "abc-123-def",
    "text": "Senior Data Analyst",
    "descriptionPlain": (
        "We're hiring a senior data analyst to drive our reporting stack. "
        "Strong SQL and Python skills expected."
    ),
    "description": "<p>HTML version</p>",
    "hostedUrl": "https://jobs.lever.co/acme/abc-123-def",
    "applyUrl": "https://jobs.lever.co/acme/abc-123-def/apply",
    "createdAt": 1714663200000,  # ms epoch — May 2024
    "categories": {
        "location": "San Francisco, CA",
        "team": "Data",
        "commitment": "Full-time",
    },
    "__slug__": "acme",
}


def _make_scraper() -> LeverScraper:
    return LeverScraper(slugs=[], sleep_between=0)


def test_normalize_maps_top_level_fields():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "lever_acme_abc-123-def"
    assert norm["title"] == "Senior Data Analyst"
    assert norm["url"] == "https://jobs.lever.co/acme/abc-123-def"
    assert "senior data analyst" in norm["body"].lower()


def test_normalize_uses_descriptionPlain_when_present():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    # descriptionPlain wins over description (HTML)
    assert "<p>" not in norm["body"]
    assert "reporting stack" in norm["body"]


def test_normalize_falls_back_to_description_when_plain_missing():
    raw = dict(SAMPLE_RAW)
    raw.pop("descriptionPlain", None)
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    assert norm["body"] == "<p>HTML version</p>"


def test_normalize_packs_metadata():
    md = _make_scraper().normalize(SAMPLE_RAW)["metadata_json"]
    assert md["company"] == "acme"
    assert md["slug"] == "acme"
    assert md["location"] == "San Francisco, CA"
    assert md["team"] == "Data"
    assert md["commitment"] == "Full-time"
    assert "citizenship_required" in md
    assert "license_required" in md
    assert "ghost_score" in md
    assert "location_normalized" in md
    assert "language_detected" in md
    assert "geo_tier" in md


def test_normalize_handles_missing_location():
    raw = dict(SAMPLE_RAW)
    raw["categories"] = {"team": "Data", "commitment": "Full-time"}
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    assert norm["metadata_json"]["location"] is None


def test_normalize_handles_missing_categories_entirely():
    raw = dict(SAMPLE_RAW)
    raw.pop("categories", None)
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    assert norm["metadata_json"]["location"] is None
    assert norm["metadata_json"]["team"] is None


def test_normalize_converts_ms_epoch_to_datetime():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2024


def test_normalize_handles_missing_createdAt():
    raw = dict(SAMPLE_RAW)
    raw.pop("createdAt", None)
    norm = _make_scraper().normalize(raw)
    assert norm["posted_at"] is None


def test_normalize_handles_invalid_createdAt():
    raw = dict(SAMPLE_RAW)
    raw["createdAt"] = "not-a-number"
    norm = _make_scraper().normalize(raw)
    assert norm["posted_at"] is None


def test_normalize_skips_missing_required_fields():
    s = _make_scraper()
    assert s.normalize({}) is None
    assert s.normalize({"id": "x"}) is None
    assert s.normalize({"text": "T"}) is None


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
        _stub_response([{"id": "1", "text": "Eng"}]),
        _stub_404(),
        _stub_response([{"id": "2", "text": "PM"}]),
    ])

    def fake_get(url, headers=None, timeout=None):
        return next(payloads)

    monkeypatch.setattr(httpx, "get", fake_get)

    s = LeverScraper(slugs=["good-1", "missing", "good-2"], sleep_between=0)
    items = s.fetch()
    assert len(items) == 2
    assert s._slugs_attempted == 3
    assert s._slugs_with_jobs == 2
    assert any(slug == "missing" for slug, _ in s._failed_slugs)
