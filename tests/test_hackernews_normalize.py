from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from scrapers.hackernews_whoishiring import HackerNewsWhoIsHiringScraper

SAMPLE_COMMENT = {
    "id": 12345,
    "by": "user123",
    "text": "Acme Corp | Data Analyst | NYC | Remote OK<p>We&#x27;re hiring.</p>",
    "time": 1714663200,
    "type": "comment",
    "parent": 99999,
}


# ----- normalize() -----


def test_normalize_extracts_title_from_first_line():
    norm = HackerNewsWhoIsHiringScraper().normalize(SAMPLE_COMMENT)
    assert norm is not None
    assert "Acme Corp" in norm["title"]
    assert "Data Analyst" in norm["title"]


def test_normalize_external_id_has_hn_prefix():
    norm = HackerNewsWhoIsHiringScraper().normalize(SAMPLE_COMMENT)
    assert norm["external_id"] == "hn_12345"


def test_normalize_extracts_company_from_pipe_split():
    norm = HackerNewsWhoIsHiringScraper().normalize(SAMPLE_COMMENT)
    assert norm["metadata_json"]["company"] == "Acme Corp"


def test_normalize_skips_deleted_comments():
    deleted = {"id": 1, "deleted": True, "text": "x", "time": 1714663200}
    assert HackerNewsWhoIsHiringScraper().normalize(deleted) is None


def test_normalize_skips_dead_comments():
    dead = {"id": 1, "dead": True, "text": "x", "time": 1714663200}
    assert HackerNewsWhoIsHiringScraper().normalize(dead) is None


def test_normalize_skips_missing_text():
    no_text = {"id": 1, "time": 1714663200}
    assert HackerNewsWhoIsHiringScraper().normalize(no_text) is None


def test_normalize_skips_missing_id():
    no_id = {"text": "Acme | Engineer", "time": 1714663200}
    assert HackerNewsWhoIsHiringScraper().normalize(no_id) is None


def test_normalize_parses_unix_timestamp():
    norm = HackerNewsWhoIsHiringScraper().normalize(SAMPLE_COMMENT)
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2024


def test_normalize_handles_invalid_timestamp():
    raw = {"id": 7, "text": "Acme | Engineer", "time": "not-a-number"}
    norm = HackerNewsWhoIsHiringScraper().normalize(raw)
    assert norm is not None
    assert norm["posted_at"] is None


def test_normalize_handles_missing_pipe_in_first_line():
    weird = {"id": 7, "text": "Some text without pipe", "time": 1714663200}
    norm = HackerNewsWhoIsHiringScraper().normalize(weird)
    assert norm is not None
    assert norm["metadata_json"]["company"] == "Unknown"


def test_normalize_url_format():
    norm = HackerNewsWhoIsHiringScraper().normalize(SAMPLE_COMMENT)
    assert norm["url"] == "https://news.ycombinator.com/item?id=12345"


# ----- fetch() with mocked HTTP -----


def _stub_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def test_fetch_walks_algolia_then_firebase(monkeypatch):
    """Algolia returns thread id 9999, Firebase returns thread (kids 1, 2),
    then comments 1 and 2. Total: 2 comments returned."""
    algolia_payload = {"hits": [{"objectID": "9999"}]}
    thread_payload = {"kids": [1, 2]}
    comment_1 = {"id": 1, "text": "A | x | y", "time": 1714663200}
    comment_2 = {"id": 2, "text": "B | x | y", "time": 1714663200}

    calls = {"i": 0}
    payloads = [algolia_payload, thread_payload, comment_1, comment_2]

    def fake_get(url, headers=None, params=None, timeout=None):
        idx = calls["i"]
        calls["i"] += 1
        return _stub_response(payloads[idx])

    monkeypatch.setattr(httpx, "get", fake_get)

    scraper = HackerNewsWhoIsHiringScraper(sleep_between=0)
    items = scraper.fetch()

    assert len(items) == 2
    assert items[0]["id"] == 1
    assert items[1]["id"] == 2
    assert scraper._thread_id == 9999


def test_fetch_returns_empty_when_no_thread_found(monkeypatch):
    algolia_empty = {"hits": []}

    def fake_get(url, headers=None, params=None, timeout=None):
        return _stub_response(algolia_empty)

    monkeypatch.setattr(httpx, "get", fake_get)
    assert HackerNewsWhoIsHiringScraper(sleep_between=0).fetch() == []


def test_fetch_caps_at_max_comments(monkeypatch):
    algolia_payload = {"hits": [{"objectID": "1"}]}
    thread_payload = {"kids": list(range(100, 110))}  # 10 comments

    queue = [algolia_payload, thread_payload] + [
        {"id": i, "text": f"Co{i} | role", "time": 1714663200}
        for i in range(100, 110)
    ]
    iterator = iter(queue)

    def fake_get(url, headers=None, params=None, timeout=None):
        return _stub_response(next(iterator))

    monkeypatch.setattr(httpx, "get", fake_get)
    items = HackerNewsWhoIsHiringScraper(max_comments=3, sleep_between=0).fetch()
    assert len(items) == 3
