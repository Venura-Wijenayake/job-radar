from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from db.database import get_session
from db.models import Item, Source


def content_hash(title: str, body: str, company: str | None) -> str:
    payload = f"{title or ''}\n{body or ''}\n{company or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
                    h = content_hash(norm["title"], norm.get("body", ""), company)

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
