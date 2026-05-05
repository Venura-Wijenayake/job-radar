"""Probe candidate Workable account slugs to confirm public job boards
exist and carry jobs before adding them to ``config/company_boards.yaml``.

Usage:
    python scripts/validate_workable_slugs.py [extra_slug ...]

Reads the current Workable slug list from the YAML and probes each, then
probes any extra slugs passed on the CLI plus a built-in candidate list.
Prints (slug, status, jobs_count) so the operator can pick which to keep.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


WORKABLE_BASE = "https://apply.workable.com/api/v1/widget/accounts"
USER_AGENT = "Mozilla/5.0 (compatible; job-radar/0.1) httpx"
SLEEP = 0.5
CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "company_boards.yaml"
)

# Candidate slugs suggested by the Phase 4.8c architect notes plus a few
# known-active extras spotted in the wild. Validation will weed out the
# duds so we only commit working slugs.
CANDIDATE_SLUGS: list[str] = [
    "parkmobile", "datadog", "deel", "coda", "ramp", "miro", "gusto",
    "plaid", "retool", "clearbit", "segment", "heap", "mixpanel",
    "hotjar", "contentful", "sanity", "prismic", "calixa", "checkr",
    "alloy", "modern-treasury", "mercury", "stripe-staffing",
    "square-staffing", "doordash-staffing", "instacart-staffing",
    "lyft-staffing", "uber-staffing", "hubspot-staffing",
    "brex-staffing",
    # Some additional commonly-active boards
    "deliveroo", "vercel", "supabase", "linear",
]


def _load_current_slugs() -> list[str]:
    if not CONFIG_PATH.exists():
        return []
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw = data.get("workable") or []
    return [str(s).strip() for s in raw if str(s).strip()]


def _probe(slug: str, client: httpx.Client) -> tuple[str, int]:
    """Return (status, jobs_count). status is HTTP status as string or
    a one-word error tag. jobs_count is 0 on any non-200."""
    url = f"{WORKABLE_BASE}/{slug}"
    try:
        r = client.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return (f"NET:{exc.__class__.__name__}", 0)
    if r.status_code != 200:
        return (f"HTTP {r.status_code}", 0)
    try:
        data: dict[str, Any] = r.json()
    except Exception:
        return ("BAD-JSON", 0)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return ("HTTP 200", len(jobs) if isinstance(jobs, list) else 0)


def main() -> None:
    extra = [a for a in sys.argv[1:] if a and not a.startswith("-")]
    current = _load_current_slugs()
    candidates = list(dict.fromkeys(current + CANDIDATE_SLUGS + extra))

    print(f"Probing {len(candidates)} Workable slugs (sleep {SLEEP}s between)")
    print(f"  current YAML: {len(current)}")
    print(f"  candidates:   {len(CANDIDATE_SLUGS)}")
    print(f"  extra (CLI):  {len(extra)}")
    print()

    with httpx.Client() as client:
        rows: list[tuple[str, str, int]] = []
        for slug in candidates:
            status, n = _probe(slug, client)
            rows.append((slug, status, n))
            tag = "current" if slug in current else "new"
            print(f"  {slug:<28} {status:<14} jobs={n:<4} ({tag})")
            time.sleep(SLEEP)

    print()
    keep = [s for s, st, n in rows if st == "HTTP 200" and n > 0]
    drop = [s for s, st, n in rows if not (st == "HTTP 200" and n > 0)]
    print(f"KEEP ({len(keep)}): {keep}")
    print(f"DROP ({len(drop)}): {drop}")


if __name__ == "__main__":
    main()
