from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from scrapers.adzuna import AdzunaScraper

SAMPLE_RAW = {
    "id": "12345",
    "title": "Junior Data Analyst",
    "description": (
        "We are looking for a junior data analyst to join our team in "
        "New York. Strong SQL and Python skills required. Visit "
        "https://example.com/careers."
    ),
    "redirect_url": "https://www.adzuna.com/jobs/details/12345",
    "created": "2026-04-15T10:30:00Z",
    "company": {"display_name": "Acme Corp"},
    "location": {"display_name": "New York, NY"},
    "salary_min": 70000.0,
    "salary_max": 90000.0,
    "category": {"label": "IT Jobs"},
    "contract_type": "permanent",
    "contract_time": "full_time",
    "__search_term__": "junior data analyst",
}


def _make_scraper() -> AdzunaScraper:
    s = AdzunaScraper(sleep_between=0)
    # Bypass _check_credentials for unit tests
    s._app_id = "test-id"
    s._app_key = "test-key"
    return s


def test_normalize_maps_top_level_fields():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "adzuna_12345"  # prefix preserved
    assert norm["title"] == "Junior Data Analyst"
    assert "junior data analyst" in norm["body"].lower()
    assert norm["url"].startswith("https://")


def test_normalize_extracts_nested_metadata():
    md = _make_scraper().normalize(SAMPLE_RAW)["metadata_json"]
    assert md["company"] == "Acme Corp"
    assert md["location"] == "New York, NY"
    assert md["category"] == "IT Jobs"
    assert md["search_term"] == "junior data analyst"
    assert md["contract_type"] == "permanent"


def test_normalize_includes_eligibility_flags():
    md = _make_scraper().normalize(SAMPLE_RAW)["metadata_json"]
    assert "citizenship_required" in md
    assert "license_required" in md
    assert "ghost_score" in md
    assert "location_normalized" in md
    assert "language_detected" in md


def test_normalize_handles_missing_salary():
    raw = dict(SAMPLE_RAW)
    raw.pop("salary_min", None)
    raw.pop("salary_max", None)
    norm = _make_scraper().normalize(raw)
    assert norm is not None
    assert norm["metadata_json"]["salary_min"] is None
    assert norm["metadata_json"]["salary_max"] is None


def test_normalize_skips_missing_required_fields():
    assert _make_scraper().normalize({}) is None
    assert _make_scraper().normalize({"id": "1"}) is None
    assert _make_scraper().normalize({"title": "T"}) is None


def test_normalize_parses_iso_date_with_z_suffix():
    norm = _make_scraper().normalize(SAMPLE_RAW)
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2026


def test_credential_check_raises_when_missing(fresh_db, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    s = AdzunaScraper(sleep_between=0)
    s._app_id = None
    s._app_key = None
    with pytest.raises(RuntimeError, match="credentials"):
        s.fetch()


def _stub_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def test_fetch_iterates_search_terms_and_pages(monkeypatch):
    """Two terms × two pages = four requests, each returning 2 items.
    fetch() should return 8 items, each tagged with the right term."""
    page_data_a1 = {"results": [{"id": "a1-1"}, {"id": "a1-2"}]}
    page_data_a2 = {"results": [{"id": "a2-1"}, {"id": "a2-2"}]}
    page_data_b1 = {"results": [{"id": "b1-1"}, {"id": "b1-2"}]}
    page_data_b2 = {"results": [{"id": "b2-1"}, {"id": "b2-2"}]}

    payloads = iter([page_data_a1, page_data_a2, page_data_b1, page_data_b2])

    def fake_get(url, headers=None, params=None, timeout=None):
        return _stub_response(next(payloads))

    monkeypatch.setattr(httpx, "get", fake_get)

    s = AdzunaScraper(
        sleep_between=0,
        pages_per_term=2,
        results_per_page=2,
        search_terms=["term-a", "term-b"],
    )
    s._app_id = "x"
    s._app_key = "y"

    items = s.fetch()
    assert len(items) == 8
    a_terms = [i for i in items if i["__search_term__"] == "term-a"]
    b_terms = [i for i in items if i["__search_term__"] == "term-b"]
    assert len(a_terms) == 4
    assert len(b_terms) == 4


def test_fetch_stops_early_on_short_page(monkeypatch):
    """When a page returns fewer results than results_per_page, the
    loop bails early without fetching further pages for that term."""
    short_page = {"results": [{"id": "1"}]}  # 1 result, but per_page=5
    next_page_should_not_be_fetched = {"results": [{"id": "ignored"}]}

    payloads = iter([short_page, next_page_should_not_be_fetched])

    def fake_get(url, headers=None, params=None, timeout=None):
        return _stub_response(next(payloads))

    monkeypatch.setattr(httpx, "get", fake_get)

    s = AdzunaScraper(
        sleep_between=0,
        pages_per_term=3,
        results_per_page=5,
        search_terms=["only-term"],
    )
    s._app_id = "x"
    s._app_key = "y"

    items = s.fetch()
    assert len(items) == 1  # only the short-page result, second page skipped
