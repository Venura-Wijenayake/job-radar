"""Run a named scraper and print its run summary."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapers.remoteok import RemoteOKScraper

SCRAPERS = {
    "remoteok": RemoteOKScraper,
}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_scraper.py <source>", file=sys.stderr)
        print(f"Available: {', '.join(SCRAPERS)}", file=sys.stderr)
        sys.exit(2)

    name = sys.argv[1].lower()
    scraper_cls = SCRAPERS.get(name)
    if scraper_cls is None:
        print(
            f"Unknown scraper: {name!r}. Available: {', '.join(SCRAPERS)}",
            file=sys.stderr,
        )
        sys.exit(2)

    summary = scraper_cls().run()
    print(summary)


if __name__ == "__main__":
    main()
