from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from db.database import get_session
from db.models import Item
from db.seed import seed_sources
from scrapers.base import _normalized_content_hash
from scrapers.remoteok import RemoteOKScraper

SAMPLE_API_RESPONSE = [
    {"legal": "metadata"},
    {
        "id": "1",
        "position": "Data Analyst",
        "company": "Acme",
        "description": "Analyze stuff.",
        "url": "https://remoteok.com/job/1",
        "epoch": 1714000000,
        "tags": ["python"],
    },
    {
        "id": "2",
        "position": "BI Analyst",
        "company": "Beta",
        "description": "BI work.",
        "url": "https://remoteok.com/job/2",
        "epoch": 1714000100,
        "tags": ["sql"],
    },
]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def seeded_db(fresh_db):
    seed_sources()
    return fresh_db


@pytest.fixture()
def stub_remoteok(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(SAMPLE_API_RESPONSE)

    monkeypatch.setattr(httpx, "get", fake_get)


def test_first_run_inserts_all_items(seeded_db, stub_remoteok):
    summary = RemoteOKScraper().run()
    assert summary == {"fetched": 2, "new": 2, "duplicates": 0, "errors": 0}

    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()
        assert len(items) == 2
        assert {i.external_id for i in items} == {"1", "2"}


def test_second_run_dedupes_everything(seeded_db, stub_remoteok):
    first = RemoteOKScraper().run()
    second = RemoteOKScraper().run()

    assert first["new"] == 2
    assert second["new"] == 0
    assert second["duplicates"] == 2
    assert second["fetched"] == 2

    with get_session() as session:
        items = session.execute(select(Item)).scalars().all()
        assert len(items) == 2


def test_content_hash_dedup_catches_cross_source_duplicates(
    seeded_db, monkeypatch
):
    """A row inserted with the same title+body+company should be deduped on the
    secondary content_hash check even if external_id differs."""
    payload_v1 = [
        {"legal": "meta"},
        {
            "id": "alpha",
            "position": "Data Analyst",
            "company": "Acme",
            "description": "Same body.",
            "url": "https://example.com/a",
            "epoch": 1714000000,
        },
    ]
    payload_v2 = [
        {"legal": "meta"},
        {
            "id": "beta",
            "position": "Data Analyst",
            "company": "Acme",
            "description": "Same body.",
            "url": "https://example.com/b",
            "epoch": 1714000100,
        },
    ]

    box = {"current": payload_v1}

    def fake_get(url, headers=None, timeout=None):
        return _FakeResponse(box["current"])

    monkeypatch.setattr(httpx, "get", fake_get)

    s1 = RemoteOKScraper().run()
    box["current"] = payload_v2
    s2 = RemoteOKScraper().run()

    assert s1["new"] == 1
    assert s2["new"] == 0
    assert s2["duplicates"] == 1


def test_normalized_hash_ignores_html_and_whitespace_formatting():
    """Identical text wrapped in different HTML / whitespace should hash
    to the same value so cross-source duplicates collapse cleanly."""
    h_plain = _normalized_content_hash(
        "Lead Analytics Engineer", "Monzo", "<p>Hello world</p>"
    )
    h_extra_space = _normalized_content_hash(
        "Lead Analytics Engineer", "Monzo", "<p>  Hello   world  </p>"
    )
    h_different_tag = _normalized_content_hash(
        "Lead Analytics Engineer", "Monzo", "<div>\n\nHello world\n\n</div>"
    )
    h_uppercased = _normalized_content_hash(
        "LEAD ANALYTICS ENGINEER", "MONZO", "<p>HELLO WORLD</p>"
    )

    assert h_plain == h_extra_space
    assert h_plain == h_different_tag
    assert h_plain == h_uppercased

    # Sanity: actually different content still produces a different hash.
    h_different_body = _normalized_content_hash(
        "Lead Analytics Engineer", "Monzo", "<p>Different content entirely.</p>"
    )
    assert h_plain != h_different_body
