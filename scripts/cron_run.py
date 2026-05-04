"""Single-entry orchestration for the daily GitHub Actions cron.

Runs init_db -> seed_sources -> all scrapers -> score -> extract,
then writes a one-line summary to ``data/cron_summary.txt`` so the
workflow can read it for the auto-commit message.

Idempotent. Safe to re-run locally, including outside CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db
from db.seed import seed_sources
from scoring.batch import extract_all_keywords, score_all_items
from scrapers.adzuna import AdzunaScraper
from scrapers.ashby import AshbyScraper
from scrapers.greenhouse import GreenhouseScraper
from scrapers.hackernews_whoishiring import HackerNewsWhoIsHiringScraper
from scrapers.lever import LeverScraper
from scrapers.remoteok import RemoteOKScraper
from scrapers.remotive import RemotiveScraper
from scrapers.weworkremotely import WeWorkRemotelyScraper
from scrapers.workable import WorkableScraper

PROFILE_NAME = "venura_data_analyst"

SCRAPERS = [
    RemoteOKScraper,
    RemotiveScraper,
    WeWorkRemotelyScraper,
    HackerNewsWhoIsHiringScraper,
    AdzunaScraper,
    GreenhouseScraper,
    LeverScraper,
    AshbyScraper,
    WorkableScraper,
]

SUMMARY_FILENAME = "cron_summary.txt"


def _summary_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / SUMMARY_FILENAME


def main() -> None:
    init_db()
    seed_sources()

    total_new = 0
    sources_with_new = 0
    per_source: list[tuple[str, dict]] = []

    for cls in SCRAPERS:
        name = cls.source_name
        try:
            summary = cls().run()
        except Exception as exc:
            print(f"[{name}] FAILED: {exc}", file=sys.stderr)
            per_source.append((name, {"errors": 1, "fetched": 0, "new": 0}))
            continue
        per_source.append((name, summary))
        new = int(summary.get("new") or 0)
        total_new += new
        if new > 0:
            sources_with_new += 1
        print(f"[{name}] {summary}")

    score_summary = score_all_items(PROFILE_NAME, force=True)
    print(f"[score] {score_summary}")

    extract_summary = extract_all_keywords(force=True)
    print(f"[extract] {extract_summary}")

    summary_line = (
        f"{total_new} new items across {sources_with_new} source(s)"
    )
    path = _summary_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary_line, encoding="utf-8")
    print(f"\nSUMMARY: {summary_line}")


if __name__ == "__main__":
    main()
