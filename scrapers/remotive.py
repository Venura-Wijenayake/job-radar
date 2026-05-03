from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from .base import BaseScraper

REMOTIVE_BASE = "https://remotive.com/api/remote-jobs"
USER_AGENT = (
    "Mozilla/5.0 (compatible; job-radar/0.1; "
    "+https://github.com/) httpx"
)


def _parse_iso(value: str | None) -> datetime | None:
    """Parse Remotive's publication_date (ISO 8601, sometimes with Z suffix)."""
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class RemotiveScraper(BaseScraper):
    """Scraper for the Remotive public JSON API.

    The data category alone misses analyst roles tagged elsewhere, so we
    hit both the data-filtered and unfiltered endpoints and let the
    BaseScraper dedup by external_id.
    """

    source_name = "Remotive"

    def __init__(self, client: httpx.Client | None = None):
        self._client = client

    def _get(self, url: str) -> dict:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._client is not None:
            response = self._client.get(url, headers=headers, timeout=30)
        else:
            response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def fetch(self) -> list[dict[str, Any]]:
        urls = [f"{REMOTIVE_BASE}?category=data", REMOTIVE_BASE]
        all_jobs: list[dict[str, Any]] = []
        for url in urls:
            try:
                payload = self._get(url)
            except Exception as exc:
                print(f"[{self.source_name}] fetch error for {url}: {exc}")
                continue
            jobs = payload.get("jobs") or []
            if isinstance(jobs, list):
                all_jobs.extend(j for j in jobs if isinstance(j, dict))
        return all_jobs

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        if not raw.get("id") or not raw.get("title"):
            return None

        metadata = {
            "company": raw.get("company_name"),
            "location": raw.get("candidate_required_location"),
            "salary": raw.get("salary"),
            "category": raw.get("category"),
            "tags": raw.get("tags") or [],
            "job_type": raw.get("job_type"),
            "remote_type": "remote",
        }

        return {
            "external_id": str(raw["id"]),
            "title": raw["title"],
            "body": raw.get("description") or "",
            "url": raw.get("url") or "",
            "metadata_json": metadata,
            "posted_at": _parse_iso(raw.get("publication_date")),
        }
