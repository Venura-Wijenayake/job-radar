"""Phase 4.8c — Himalayas scraper normalize() tests.

The Himalayas API returns ``guid`` (a stable URL) as the canonical
identifier and stores HTML in ``description``. ``pubDate`` is Unix
epoch seconds. ``locationRestrictions`` is a list of country names —
absent restrictions imply worldwide-remote, which the scraper should
default to "Remote" rather than dropping the location entirely.
"""
from __future__ import annotations

from scrapers.himalayas import HimalayasScraper

SAMPLE_RAW = {
    "guid": "https://himalayas.app/companies/foocorp/jobs/data-analyst",
    "applicationLink": "https://himalayas.app/companies/foocorp/jobs/data-analyst",
    "title": "Data Analyst",
    "companyName": "FooCorp",
    "companySlug": "foocorp",
    "description": "<p>We're hiring a <strong>data analyst</strong>.</p>",
    "excerpt": "We're hiring a data analyst.",
    "locationRestrictions": ["United States"],
    "pubDate": 1714663200,
    "expiryDate": 1717255200,
    "minSalary": 80000,
    "maxSalary": 120000,
    "currency": "USD",
    "employmentType": "Full Time",
    "seniority": ["Mid-level"],
    "categories": ["Data-Analysis"],
}


def test_normalize_maps_top_level_fields():
    norm = HimalayasScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"].startswith("himalayas_")
    assert "foocorp" in norm["external_id"]  # guid path includes companySlug
    assert norm["title"] == "Data Analyst"
    assert norm["url"] == SAMPLE_RAW["applicationLink"]
    assert norm["posted_at"] is not None


def test_normalize_handles_html_in_description():
    """Body should land as plain text — clean_html strips the <p> /
    <strong> wrapping."""
    norm = HimalayasScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    body = norm["body"]
    assert "<p>" not in body
    assert "<strong>" not in body
    assert "data analyst" in body.lower()


def test_normalize_unescapes_entities():
    """HTML entities (``&amp;``, ``&#39;``) need to land as the actual
    characters, not literal entities, so downstream keyword extraction
    sees the right tokens."""
    raw = {
        **SAMPLE_RAW,
        "description": "<p>Tools &amp; tech: don&#39;t miss this</p>",
    }
    norm = HimalayasScraper().normalize(raw)
    assert norm is not None
    body = norm["body"]
    assert "&amp;" not in body
    assert "&#39;" not in body
    assert "&" in body
    assert "don't" in body


def test_normalize_extracts_remote_flag_from_empty_location():
    """Most Himalayas postings carry no ``locationRestrictions`` —
    treat that as worldwide-remote rather than dropping the field."""
    raw = {**SAMPLE_RAW, "locationRestrictions": None}
    norm = HimalayasScraper().normalize(raw)
    assert norm is not None
    md = norm["metadata_json"]
    assert md["is_remote"] is True
    assert md["remote_type"] == "remote"
    assert md["location"] == "Remote"


def test_normalize_handles_locationsAlternatives_array():
    """Multi-country restrictions are joined into a comma-separated
    location string so normalize_location can bucket the geo tier."""
    raw = {
        **SAMPLE_RAW,
        "locationRestrictions": ["United States", "Canada"],
    }
    norm = HimalayasScraper().normalize(raw)
    assert norm is not None
    location = norm["metadata_json"]["location"]
    assert "United States" in location
    assert "Canada" in location


def test_normalize_parses_publishedAt_iso8601():
    """``pubDate`` is Unix epoch seconds — a 2024 timestamp (1714663200)
    should round-trip to a sensible 2024 datetime."""
    norm = HimalayasScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    posted = norm["posted_at"]
    assert posted is not None
    assert posted.year == 2024
    assert posted.month == 5  # May 2024 from 1714663200


def test_normalize_extracts_salary_when_present():
    norm = HimalayasScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    md = norm["metadata_json"]
    assert md["salary_min"] == 80000
    assert md["salary_max"] == 120000
    assert md["salary_currency"] == "USD"


def test_normalize_handles_missing_optional_fields():
    """Minimum required = guid + title. Everything else defaults to
    None / [] / 'Remote'."""
    minimal = {
        "guid": "https://himalayas.app/companies/x/jobs/y",
        "title": "Analyst",
    }
    norm = HimalayasScraper().normalize(minimal)
    assert norm is not None
    assert norm["body"] == ""
    assert norm["posted_at"] is None
    md = norm["metadata_json"]
    assert md["salary_min"] is None
    assert md["salary_max"] is None
    assert md["categories"] == []
    assert md["seniority"] == []


def test_normalize_skips_records_missing_required_fields():
    scraper = HimalayasScraper()
    # Title without any id form -> skipped
    assert scraper.normalize({"title": "No id"}) is None
    # Id form without title -> skipped
    assert scraper.normalize({"guid": "x"}) is None


def test_normalize_assigns_search_term_aggregator_label():
    norm = HimalayasScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["metadata_json"]["search_term"] == "himalayas_aggregator"
