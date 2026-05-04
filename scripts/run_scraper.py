"""Run a single scraper or all enabled sources in sequence."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import get_session
from db.models import Source
from scrapers.adzuna import AdzunaScraper
from scrapers.ashby import AshbyScraper
from scrapers.greenhouse import GreenhouseScraper
from scrapers.hackernews_whoishiring import HackerNewsWhoIsHiringScraper
from scrapers.lever import LeverScraper
from scrapers.remoteok import RemoteOKScraper
from scrapers.remotive import RemotiveScraper
from scrapers.weworkremotely import WeWorkRemotelyScraper

# Map source_name (matches db Sources rows) to scraper class.
SCRAPERS = {
    "RemoteOK": RemoteOKScraper,
    "Remotive": RemotiveScraper,
    "WeWorkRemotely": WeWorkRemotelyScraper,
    "HackerNewsWhoIsHiring": HackerNewsWhoIsHiringScraper,
    "Adzuna": AdzunaScraper,
    "Greenhouse": GreenhouseScraper,
    "Lever": LeverScraper,
    "Ashby": AshbyScraper,
}

# Lowercase short aliases for the CLI single-source form.
ALIASES = {
    "remoteok": "RemoteOK",
    "remotive": "Remotive",
    "weworkremotely": "WeWorkRemotely",
    "wwr": "WeWorkRemotely",
    "hackernews": "HackerNewsWhoIsHiring",
    "hackernewswhoishiring": "HackerNewsWhoIsHiring",
    "hn": "HackerNewsWhoIsHiring",
    "adzuna": "Adzuna",
    "greenhouse": "Greenhouse",
    "gh": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
}


def _enabled_sources_in_db() -> list[str]:
    """Return source_names that exist in the DB and have an associated scraper."""
    with get_session() as session:
        names = (
            session.execute(
                select(Source.name).where(Source.enabled.is_(True))
            )
            .scalars()
            .all()
        )
    return [n for n in names if n in SCRAPERS]


def _run_one(name: str) -> dict:
    cls = SCRAPERS[name]
    return cls().run()


def _print_one(name: str, summary: dict | str) -> None:
    print(f"  {name:<24} {summary}")


def _usage() -> None:
    available = ", ".join(sorted(ALIASES))
    print(
        "Usage: python scripts/run_scraper.py <source>|--all\n"
        f"Sources: {available}",
        file=sys.stderr,
    )


def main() -> None:
    if len(sys.argv) < 2:
        _usage()
        sys.exit(2)

    arg = sys.argv[1].lower()

    if arg == "--all":
        sources = _enabled_sources_in_db()
        print(f"Running {len(sources)} scrapers")
        results: list[tuple[str, dict]] = []
        total_new = 0
        for name in sources:
            try:
                summary = _run_one(name)
            except Exception as exc:
                _print_one(name, f"FAILED: {exc}")
                continue
            results.append((name, summary))
            total_new += int(summary.get("new") or 0)
        print()
        for name, summary in results:
            _print_one(name, summary)
        print("-" * 70)
        print(f"  TOTAL{'':<19} new: {total_new} across {len(results)} source(s)")
        return

    name = ALIASES.get(arg)
    if name is None:
        _usage()
        sys.exit(2)
    print(_run_one(name))


if __name__ == "__main__":
    main()
