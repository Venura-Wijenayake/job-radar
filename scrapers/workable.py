from __future__ import annotations

import html
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from scoring.eligibility_utils import (
    detect_citizenship_required,
    detect_license_required,
)
from scoring.ghost_utils import compute_ghost_score
from scoring.language_utils import detect_language
from scoring.location_utils import classify_geo_tier, normalize_location
from scoring.text_utils import clean_html

from .base import BaseScraper

WORKABLE_BASE = "https://apply.workable.com/api/v1/widget/accounts"
USER_AGENT = (
    "Mozilla/5.0 (compatible; job-radar/0.1; "
    "+https://github.com/) httpx"
)
DEFAULT_INTER_REQUEST_SLEEP = 0.5
CONFIG_FILENAME = "company_boards.yaml"


def _load_slugs() -> list[str]:
    """Load Workable slug list from config/company_boards.yaml."""
    config_path = (
        Path(__file__).resolve().parent.parent / "config" / CONFIG_FILENAME
    )
    if not config_path.exists():
        return []
    with open(config_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw = data.get("workable") or []
    return [str(s).strip() for s in raw if str(s).strip()]


def _parse_iso(value: str | None) -> datetime | None:
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


def _build_location_string(loc: dict[str, Any] | None) -> str | None:
    """Compose a human-readable location string from Workable's structured
    location object: ``{city, region, country, countryCode, workplace}``.
    Returns None if every part is missing.
    """
    if not isinstance(loc, dict):
        return None
    parts: list[str] = []
    for key in ("city", "region", "country"):
        val = loc.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    return ", ".join(parts) if parts else None


class WorkableScraper(BaseScraper):
    """Scraper for Workable public job boards.

    Iterates a curated slug list (config/company_boards.yaml). Each slug
    hits ``apply.workable.com/api/v1/widget/accounts/{slug}``. The widget
    endpoint is a single GET with no pagination — the full active board
    arrives in one response. 404 / network / JSON errors are logged
    per-slug and skipped; an empty ``jobs`` list is logged but not
    treated as an error.
    """

    source_name = "Workable"

    def __init__(
        self,
        client: httpx.Client | None = None,
        slugs: list[str] | None = None,
        sleep_between: float = DEFAULT_INTER_REQUEST_SLEEP,
    ):
        self._client = client
        self._slugs = slugs if slugs is not None else _load_slugs()
        self._sleep = sleep_between
        self._failed_slugs: list[tuple[str, str]] = []
        self._slugs_with_jobs = 0
        self._slugs_attempted = 0
        self._current_slug: str | None = None

    def _get(self, url: str) -> dict[str, Any]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self._client is not None:
            response = self._client.get(url, headers=headers, timeout=30)
        else:
            response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def fetch(self) -> list[dict[str, Any]]:
        all_jobs: list[dict[str, Any]] = []
        self._failed_slugs = []
        self._slugs_with_jobs = 0
        self._slugs_attempted = 0

        for slug in self._slugs:
            self._slugs_attempted += 1
            self._current_slug = slug
            url = f"{WORKABLE_BASE}/{slug}"
            try:
                payload = self._get(url)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response else None
                if status == 404:
                    print(f"[Workable] slug not found: {slug}")
                else:
                    print(f"[Workable] HTTP {status} for {slug}")
                self._failed_slugs.append((slug, f"HTTP {status}"))
                if self._sleep > 0:
                    time.sleep(self._sleep)
                continue
            except Exception as exc:
                print(f"[Workable] fetch error for {slug}: {exc}")
                self._failed_slugs.append((slug, str(exc)))
                if self._sleep > 0:
                    time.sleep(self._sleep)
                continue

            # Workable wraps the company name at the response top-level.
            # Tag each job so normalise() can use it without a re-fetch.
            account = payload.get("account") or payload
            company_name = (
                account.get("name") if isinstance(account, dict) else None
            )

            jobs = payload.get("jobs") or []
            if isinstance(jobs, list):
                count_before = len(all_jobs)
                for j in jobs:
                    if isinstance(j, dict):
                        j["__slug__"] = slug
                        j["__company_name__"] = company_name
                        all_jobs.append(j)
                if len(all_jobs) > count_before:
                    self._slugs_with_jobs += 1
                else:
                    print(f"[Workable] 0 jobs for {slug}")

            if self._sleep > 0:
                time.sleep(self._sleep)

        self._current_slug = None
        return all_jobs

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        job_id = raw.get("id") or raw.get("shortcode")
        title = raw.get("title")
        if not job_id or not title:
            return None

        slug = raw.get("__slug__") or "unknown"

        # Body = description + requirements + benefits (all HTML, often
        # entity-encoded). Concatenate before stripping so a single pass
        # of clean_html handles the lot.
        body_parts: list[str] = []
        for key in ("description", "requirements", "benefits"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                body_parts.append(val)
        body_raw = "\n\n".join(body_parts)
        body = clean_html(html.unescape(body_raw)) if body_raw else ""

        # Workable's location is a structured object. Build a display
        # string for the dashboard and let normalize_location bucket it.
        loc_obj = raw.get("location") if isinstance(raw.get("location"), dict) else None
        location_str = _build_location_string(loc_obj)
        workplace = (
            (loc_obj or {}).get("workplace") if loc_obj else None
        )
        if isinstance(workplace, str) and workplace.lower() == "remote":
            # Append a "Remote" hint so normalize_location can bucket
            # remote-only postings even if city/region were empty.
            location_str = (
                f"Remote, {location_str}" if location_str else "Remote"
            )

        department = (
            raw.get("department")
            if isinstance(raw.get("department"), str)
            else None
        )
        employment_type = (
            raw.get("employment_type")
            if isinstance(raw.get("employment_type"), str)
            else None
        )

        posted_at_val = _parse_iso(
            raw.get("published") or raw.get("created_at")
        )

        # Company name comes from the account-level field grafted into
        # the job dict by fetch(). Falls back to a title-cased slug.
        company = raw.get("__company_name__") or slug.title()
        url = (
            raw.get("application_url")
            or raw.get("shortlink")
            or raw.get("url")
            or ""
        )

        metadata = {
            "company": company,
            "slug": slug,
            "location": location_str,
            "department": department,
            "employment_type": employment_type,
            "workplace": workplace if isinstance(workplace, str) else None,
            "search_term": "direct_board",
            "remote_type": "varied",
            "location_normalized": normalize_location(location_str, body),
            "geo_tier": classify_geo_tier(location_str, body),
            "language_detected": detect_language(body),
            "citizenship_required": detect_citizenship_required(body),
            "license_required": detect_license_required(body),
            "ghost_score": compute_ghost_score(
                {
                    "title": title,
                    "body": body,
                    "company": company,
                    "posted_at": posted_at_val,
                }
            ),
        }

        return {
            "external_id": f"workable_{slug}_{job_id}",
            "title": title,
            "body": body,
            "url": url,
            "metadata_json": metadata,
            "posted_at": posted_at_val,
        }
