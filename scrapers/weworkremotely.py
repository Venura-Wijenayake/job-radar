from __future__ import annotations

from datetime import datetime
from time import struct_time
from typing import Any

import feedparser
import httpx

from .base import BaseScraper

WWR_URL = "https://weworkremotely.com/remote-jobs.rss"
USER_AGENT = (
    "Mozilla/5.0 (compatible; job-radar/0.1; "
    "+https://github.com/) httpx"
)


def _struct_to_naive_utc(st: struct_time | None) -> datetime | None:
    """feedparser normalizes struct_time to UTC; just promote to datetime."""
    if st is None:
        return None
    try:
        return datetime(*st[:6])
    except (TypeError, ValueError):
        return None


class WeWorkRemotelyScraper(BaseScraper):
    """Scraper for the WeWorkRemotely RSS feed.

    WWR titles follow the convention "Company Name: Role Title". We split
    on the first colon — if there is no colon, the whole string is the
    role and company is empty.
    """

    source_name = "WeWorkRemotely"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def fetch(self) -> list[dict[str, Any]]:
        headers = {"User-Agent": USER_AGENT}
        if self._client is not None:
            response = self._client.get(WWR_URL, headers=headers, timeout=30)
        else:
            response = httpx.get(WWR_URL, headers=headers, timeout=30)
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        return list(feed.entries)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        link = raw.get("link") or ""
        external_id = raw.get("id") or link
        if not external_id:
            return None

        full_title = raw.get("title") or ""
        if ":" in full_title:
            company, _, title_part = full_title.partition(":")
            company = company.strip()
            title = title_part.strip()
        else:
            company = ""
            title = full_title.strip()

        if not title:
            return None

        tags: list[str] = []
        raw_tags = raw.get("tags") or []
        for tag in raw_tags:
            if isinstance(tag, dict):
                term = tag.get("term") or ""
            else:
                term = getattr(tag, "term", "") or ""
            if term:
                tags.append(term)

        metadata = {
            "company": company,
            "tags": tags,
            "region": raw.get("region"),
            "remote_type": "remote",
        }

        return {
            "external_id": str(external_id),
            "title": title,
            "body": raw.get("description") or raw.get("summary") or "",
            "url": link,
            "metadata_json": metadata,
            "posted_at": _struct_to_naive_utc(raw.get("published_parsed")),
        }
