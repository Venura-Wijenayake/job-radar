"""Extract per-item keyword lists into the keyword_extracts table."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.batch import extract_all_keywords


def main() -> None:
    force = "--force" in sys.argv[1:]
    summary = extract_all_keywords(force=force)
    print(summary)


if __name__ == "__main__":
    main()
