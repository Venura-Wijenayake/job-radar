from __future__ import annotations

from scrapers.remoteok import RemoteOKScraper

SAMPLE_RAW = {
    "id": "abc123",
    "position": "Senior Data Analyst",
    "company": "Acme Corp",
    "description": "We're hiring a senior analyst.",
    "url": "https://remoteok.com/job/abc123",
    "epoch": 1714663200,
    "tags": ["python", "sql"],
    "salary_min": 80000,
    "salary_max": 120000,
    "location": "Worldwide",
    "logo": "https://example.com/logo.png",
}


def test_normalize_maps_all_top_level_fields():
    norm = RemoteOKScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "abc123"
    assert norm["title"] == "Senior Data Analyst"
    assert norm["body"] == "We're hiring a senior analyst."
    assert norm["url"] == "https://remoteok.com/job/abc123"
    assert norm["posted_at"] is not None


def test_normalize_packs_metadata():
    norm = RemoteOKScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    md = norm["metadata_json"]
    assert md["company"] == "Acme Corp"
    assert md["location"] == "Worldwide"
    assert md["salary_min"] == 80000
    assert md["salary_max"] == 120000
    assert md["tags"] == ["python", "sql"]
    assert md["logo"] == "https://example.com/logo.png"
    assert md["remote_type"] == "remote"


def test_normalize_skips_records_missing_required_fields():
    scraper = RemoteOKScraper()
    assert scraper.normalize({"position": "No id"}) is None
    assert scraper.normalize({"id": "1"}) is None


def test_normalize_handles_missing_optional_fields():
    minimal = {"id": "x", "position": "Analyst"}
    norm = RemoteOKScraper().normalize(minimal)
    assert norm is not None
    assert norm["body"] == ""
    assert norm["posted_at"] is None
    assert norm["metadata_json"]["tags"] == []


def test_normalize_handles_invalid_epoch():
    raw = {"id": "x", "position": "Analyst", "epoch": "not-a-number"}
    norm = RemoteOKScraper().normalize(raw)
    assert norm is not None
    assert norm["posted_at"] is None
