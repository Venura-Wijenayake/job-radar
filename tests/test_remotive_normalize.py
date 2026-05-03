from __future__ import annotations

from scrapers.remotive import RemotiveScraper

SAMPLE_RAW = {
    "id": 12345,
    "title": "Senior Data Analyst",
    "company_name": "Acme Corp",
    "category": "Data",
    "tags": ["python", "sql"],
    "salary": "$80k-$120k",
    "candidate_required_location": "Worldwide",
    "publication_date": "2024-05-02T10:30:00",
    "description": "<p>We are hiring a senior analyst.</p>",
    "url": "https://remotive.com/remote-jobs/data/abc",
    "job_type": "full_time",
}


def test_normalize_maps_top_level_fields():
    norm = RemotiveScraper().normalize(SAMPLE_RAW)
    assert norm is not None
    assert norm["external_id"] == "12345"
    assert norm["title"] == "Senior Data Analyst"
    assert "<p>" in norm["body"]
    assert norm["url"] == "https://remotive.com/remote-jobs/data/abc"


def test_normalize_packs_metadata():
    norm = RemotiveScraper().normalize(SAMPLE_RAW)
    md = norm["metadata_json"]
    assert md["company"] == "Acme Corp"
    assert md["category"] == "Data"
    assert md["tags"] == ["python", "sql"]
    assert md["salary"] == "$80k-$120k"
    assert md["location"] == "Worldwide"
    assert md["job_type"] == "full_time"


def test_normalize_parses_iso_date():
    norm = RemotiveScraper().normalize(SAMPLE_RAW)
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2024
    assert norm["posted_at"].month == 5


def test_normalize_handles_z_suffix_iso_date():
    raw = {"id": 1, "title": "T", "publication_date": "2024-05-02T10:30:00Z"}
    norm = RemotiveScraper().normalize(raw)
    assert norm["posted_at"] is not None


def test_normalize_handles_missing_salary():
    minimal = {"id": 1, "title": "T", "publication_date": "2024-01-01T00:00:00"}
    norm = RemotiveScraper().normalize(minimal)
    assert norm is not None
    assert norm["metadata_json"]["salary"] is None


def test_normalize_handles_missing_tags():
    minimal = {"id": 1, "title": "T"}
    norm = RemotiveScraper().normalize(minimal)
    assert norm is not None
    assert norm["metadata_json"]["tags"] == []


def test_normalize_handles_invalid_iso_date():
    raw = {"id": 1, "title": "T", "publication_date": "not-a-date"}
    norm = RemotiveScraper().normalize(raw)
    assert norm["posted_at"] is None


def test_normalize_skips_missing_required_fields():
    assert RemotiveScraper().normalize({}) is None
    assert RemotiveScraper().normalize({"id": 1}) is None
    assert RemotiveScraper().normalize({"title": "T"}) is None
