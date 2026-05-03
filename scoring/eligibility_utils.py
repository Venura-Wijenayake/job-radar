"""Detect citizenship-required and license-required gating language.

Both detectors return False on empty input. Both look for *restrictive*
phrasing only — inclusive language ("US citizens, GCs, and visa holders
welcome") is not a hit.
"""
from __future__ import annotations

from .text_utils import term_pattern

# Citizenship / clearance gating language. Each entry must indicate a
# *restriction* on who can take the role, not an inclusive description
# of who's welcome to apply.
CITIZENSHIP_PATTERNS: list[str] = [
    "must be us citizen",
    "must be a us citizen",
    "must be u.s. citizen",
    "us citizen only",
    "u.s. citizen only",
    "us citizens only",
    "us citizenship required",
    "u.s. citizenship required",
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
    "no sponsorship",
    "unable to sponsor",
    "cannot sponsor",
    "we do not sponsor",
    "we cannot sponsor",
    "we are unable to sponsor",
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
    language. ``None`` or empty returns False."""
    if not text:
        return False
    return _has_any(text, CITIZENSHIP_PATTERNS)


def detect_license_required(text: str | None) -> bool:
    """Returns True iff the text *requires* a driver's license / vehicle.
    Aspirational language ("willing to travel", "occasional driving")
    is not a hit. ``None`` or empty returns False."""
    if not text:
        return False
    return _has_any(text, LICENSE_PATTERNS)
