from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from db.database import get_session
from db.models import Item, Source
from scoring.text_utils import clean_html, normalize_unicode


def _normalized_content_hash(title: str, company: str | None, body: str) -> str:
    """Content hash resilient to HTML/whitespace formatting noise.

    Strips HTML from body, unicode-normalizes, lowercases, collapses
    whitespace, and truncates the body to its first 500 cleaned chars
    so trailing boilerplate variations (footer links, "Apply now"
    banners) don't break the hash. Two items posted to different
    sources with the same job description but slightly different
    HTML wrapping will hash identically.
    """
    cleaned_body = normalize_unicode(clean_html(body or ""))
    body_part = cleaned_body[:500]
    title_part = normalize_unicode(title or "")
    company_part = normalize_unicode(company or "")

    combined = f"{title_part}\n{company_part}\n{body_part}"
    normalized = re.sub(r"\s+", " ", combined.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseScraper(ABC):
    """Abstract scraper. Subclasses set `source_name` and implement
    `fetch()` (raw items) and `normalize()` (raw -> items-schema dict).

    `run()` orchestrates fetch -> normalize -> dedup -> insert and updates
    `sources.last_run_at` on completion.
    """

    source_name: str = ""

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        ...

    def _get_source(self, session) -> Source:
        source = session.execute(
            select(Source).where(Source.name == self.source_name)
        ).scalar_one_or_none()
        if source is None:
            raise RuntimeError(
                f"Source {self.source_name!r} not seeded. "
                "Run scripts/init_db.py first."
            )
        return source

    def run(self) -> dict[str, int]:
        summary = {"fetched": 0, "new": 0, "duplicates": 0, "errors": 0}

        try:
            raw_items = self.fetch()
        except Exception as exc:
            summary["errors"] = 1
            print(f"[{self.source_name}] fetch error: {exc}")
            return summary

        summary["fetched"] = len(raw_items)

        with get_session() as session:
            source = self._get_source(session)

            for raw in raw_items:
                try:
                    norm = self.normalize(raw)
                    if norm is None:
                        continue

                    company = (norm.get("metadata_json") or {}).get("company")
                    h = _normalized_content_hash(
                        norm["title"], company, norm.get("body", "")
                    )

                    # Primary dedup: same source + external_id
                    existing = session.execute(
                        select(Item).where(
                            Item.source_id == source.id,
                            Item.external_id == str(norm["external_id"]),
                        )
                    ).scalar_one_or_none()
                    if existing is not None:
                        summary["duplicates"] += 1
                        continue

                    # Secondary dedup: identical content already seen (cross-source)
                    existing_by_hash = session.execute(
                        select(Item).where(Item.content_hash == h)
                    ).scalar_one_or_none()
                    if existing_by_hash is not None:
                        summary["duplicates"] += 1
                        continue

                    session.add(
                        Item(
                            source_id=source.id,
                            external_id=str(norm["external_id"]),
                            title=norm["title"],
                            body=norm.get("body", ""),
                            url=norm["url"],
                            metadata_json=norm.get("metadata_json"),
                            posted_at=norm.get("posted_at"),
                            content_hash=h,
                        )
                    )
                    session.flush()
                    summary["new"] += 1
                except Exception as exc:
                    summary["errors"] += 1
                    print(f"[{self.source_name}] normalize/insert error: {exc}")

            source.last_run_at = _now_utc_naive()
            session.commit()

        return summary
