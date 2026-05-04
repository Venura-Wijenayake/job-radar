"""Detect citizenship-required and license-required gating language.

Both detectors return False on empty input. Both look for *restrictive*
phrasing only — inclusive language ("US citizens, GCs, and visa holders
welcome") is not a hit.

Phase 4.6b adds an inclusive-override list to detect_citizenship_required
so that "Must be US citizen or permanent resident" / "authorized to
work in the US" phrasing returns False even when a restrictive-pattern
substring is also present. Permanent residents and US-authorized non-
citizens fit the user's eligibility, so these JDs shouldn't get filtered
out as citizenship-required.
"""
from __future__ import annotations

from .text_utils import term_pattern

# Citizenship / sponsorship gating language. Each entry indicates a
# *restriction* on who can take the role, not an inclusive description
# of who's welcome to apply. Clearance language is split out below
# because clearance-required roles can never be overridden.
CITIZENSHIP_PATTERNS: list[str] = [
    "must be us citizen",
    "must be a us citizen",
    "must be u.s. citizen",
    "us citizen only",
    "u.s. citizen only",
    "us citizens only",
    "us citizenship required",
    "u.s. citizenship required",
    "no sponsorship",
    "unable to sponsor",
    "cannot sponsor",
    "we do not sponsor",
    "we cannot sponsor",
    "we are unable to sponsor",
]

# Clearance language. Hard-restrictive: a TS/SCI or polygraph role is
# inaccessible regardless of any inclusive wording elsewhere in the
# JD, so detect_citizenship_required short-circuits when one of these
# matches before the inclusive-override check runs.
CLEARANCE_PATTERNS: list[str] = [
    "active security clearance",
    "active clearance",
    "secret clearance",
    "top secret",
    "ts/sci",
    "ts sci",
    "public trust clearance",
    "doe q clearance",
    "polygraph",
    "ability to obtain clearance",
    "must be able to obtain clearance",
    "clearance required",
    "clearance is required",
]

# Inclusive phrasing — when present, the JD welcomes permanent residents
# and US-authorized applicants, so the restrictive patterns above
# should NOT mark the role as citizenship-required.
CITIZENSHIP_INCLUSIVE_PATTERNS: list[str] = [
    "us citizen or permanent resident",
    "u.s. citizen or permanent resident",
    "us citizens or permanent residents",
    "u.s. citizens or permanent residents",
    "us citizens, green card holders",
    "us citizens, gcs",
    "us citizens and lawful permanent residents",
    "u.s. citizens and lawful permanent residents",
    "authorized to work in the united states",
    "authorized to work in the us",
    "authorized to work in the u.s.",
    "must be authorized to work in the us",
    "authorized to work in the us without sponsorship",
    "no visa sponsorship",
    "without requiring sponsorship",
    "without sponsorship now or in the future",
]


# License / vehicle requirements
LICENSE_PATTERNS: list[str] = [
    "valid driver's license required",
    "valid drivers license required",
    "driver's license required",
    "drivers license required",
    "must have valid driver's license",
    "must have valid drivers license",
    "must possess driver's license",
    "must possess drivers license",
    "cdl required",
    "commercial driver's license",
    "commercial drivers license",
    "personal vehicle required",
    "must have own vehicle",
    "must have a personal vehicle",
    "reliable transportation required",
    "must have reliable transportation",
]


def _has_any(text: str, patterns: list[str]) -> bool:
    for p in patterns:
        if term_pattern(p).search(text):
            return True
    return False


def detect_citizenship_required(text: str | None) -> bool:
    """Returns True iff the text contains citizenship/clearance gating
    language. ``None`` or empty returns False.

    Inclusive override: even if a restrictive substring matches, the
    detector returns False when the JD also says something like "US
    citizen or permanent resident" — permanent residents and other
    US-authorized applicants fit the eligibility. Active security
    clearances always count as restrictive (no inclusive override
    overrides clearance language)."""
    if not text:
        return False

    # Clearance language is always restrictive — no override should
    # make a TS/SCI / polygraph role appear unrestricted.
    if _has_any(text, CLEARANCE_PATTERNS):
        return True

    if _has_any(text, CITIZENSHIP_INCLUSIVE_PATTERNS):
        return False

    return _has_any(text, CITIZENSHIP_PATTERNS)


def detect_license_required(text: str | None) -> bool:
    """Returns True iff the text *requires* a driver's license / vehicle.
    Aspirational language ("willing to travel", "occasional driving")
    is not a hit. ``None`` or empty returns False."""
    if not text:
        return False
    return _has_any(text, LICENSE_PATTERNS)
