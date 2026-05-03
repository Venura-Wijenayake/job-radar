from __future__ import annotations

import feedparser

from scrapers.weworkremotely import WeWorkRemotelyScraper

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>WWR</title>
<item>
  <title>Acme Corp: Senior Data Analyst</title>
  <link>https://weworkremotely.com/remote-jobs/abc-123</link>
  <description>&lt;p&gt;Looking for an analyst.&lt;/p&gt;</description>
  <pubDate>Fri, 02 May 2024 10:00:00 +0000</pubDate>
  <guid>https://weworkremotely.com/remote-jobs/abc-123</guid>
  <category>Data</category>
</item>
<item>
  <title>StandaloneTitleNoColon</title>
  <link>https://weworkremotely.com/remote-jobs/xyz-456</link>
  <description>Body text.</description>
  <pubDate>Fri, 02 May 2024 10:00:00 +0000</pubDate>
  <guid>https://weworkremotely.com/remote-jobs/xyz-456</guid>
</item>
</channel>
</rss>
"""


def _entries() -> list:
    return list(feedparser.parse(SAMPLE_RSS).entries)


def test_normalize_parses_company_role_split():
    norm = WeWorkRemotelyScraper().normalize(_entries()[0])
    assert norm is not None
    assert norm["title"] == "Senior Data Analyst"
    assert norm["metadata_json"]["company"] == "Acme Corp"


def test_normalize_handles_no_colon_in_title():
    norm = WeWorkRemotelyScraper().normalize(_entries()[1])
    assert norm is not None
    assert norm["title"] == "StandaloneTitleNoColon"
    assert norm["metadata_json"]["company"] == ""


def test_normalize_uses_link_or_guid_for_external_id():
    norm = WeWorkRemotelyScraper().normalize(_entries()[0])
    assert "abc-123" in norm["external_id"]


def test_normalize_parses_published_date():
    norm = WeWorkRemotelyScraper().normalize(_entries()[0])
    assert norm["posted_at"] is not None
    assert norm["posted_at"].year == 2024
    assert norm["posted_at"].month == 5


def test_normalize_returns_none_on_empty_title():
    fake = {"title": "", "link": "http://x", "id": "x", "description": "d"}
    assert WeWorkRemotelyScraper().normalize(fake) is None


def test_normalize_returns_none_on_missing_id_and_link():
    fake = {"title": "Acme: Engineer"}
    assert WeWorkRemotelyScraper().normalize(fake) is None


def test_normalize_falls_back_to_link_when_id_absent():
    fake = {
        "title": "Acme: Engineer",
        "link": "http://example.com/job/1",
        "description": "body",
    }
    norm = WeWorkRemotelyScraper().normalize(fake)
    assert norm is not None
    assert norm["external_id"] == "http://example.com/job/1"
