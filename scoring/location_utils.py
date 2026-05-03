"""Best-effort offline location bucketing.

``normalize_location(raw, body=None)`` returns one of:
    Remote-US | Remote-Global | US | EU | UK | Canada | India |
    Brazil | LatAm | Asia-Other | Africa | Australia/NZ | Unknown

Order matters: Remote-US is checked before Remote-Global so an
explicit US-only remote post doesn't fall into the global bucket.

No external geocoding APIs — all matching uses word-boundary
patterns from text_utils.term_pattern, so 2-letter state codes
like "CA" don't false-match inside words like "Canada".
"""
from __future__ import annotations

from typing import Iterable

from .text_utils import term_pattern

LOCATION_RULES: list[tuple[str, list[str]]] = [
    (
        "Remote-US",
        [
            "remote (us)", "remote us", "remote, us", "remote - us",
            "us-only", "us only", "united states only",
            "remote in the us", "remote in us", "remote within us",
            "us residents only", "us-based", "us based",
        ],
    ),
    (
        "Remote-Global",
        [
            "remote", "worldwide", "anywhere", "global",
            "fully remote", "100% remote",
        ],
    ),
    (
        "US",
        [
            "united states", "usa", "u.s.a", "u.s.",
            # Major cities
            "new york", "nyc", "los angeles", "san francisco",
            "chicago", "houston", "phoenix", "philadelphia",
            "san diego", "dallas", "austin", "boston", "seattle",
            "denver", "atlanta", "miami", "portland", "minneapolis",
            "detroit", "baltimore", "milwaukee", "sacramento",
            "kansas city", "las vegas", "raleigh", "tampa",
            "washington dc", "washington d.c.",
            # Full state names — bare 2-letter state codes are deliberately
            # excluded because they collide with everyday words and
            # foreign place names (e.g. "DE" in "Rio de Janeiro", "MA",
            # "OR", "IN"). Full-name coverage is sufficient when paired
            # with city names; the regex word-boundary still protects
            # against substring matches.
            "california", "texas", "florida", "pennsylvania",
            "illinois", "ohio", "north carolina", "michigan",
            "new jersey", "virginia", "arizona", "tennessee",
            "massachusetts", "indiana", "missouri", "maryland",
            "wisconsin", "colorado", "minnesota", "south carolina",
            "alabama", "louisiana", "kentucky", "oregon", "oklahoma",
            "connecticut", "utah", "iowa", "nevada", "arkansas",
            "mississippi", "kansas", "new mexico", "nebraska",
            "west virginia", "idaho", "hawaii", "new hampshire",
            "maine", "montana", "rhode island", "delaware",
            "south dakota", "north dakota", "alaska", "vermont",
            "wyoming",
        ],
    ),
    (
        "EU",
        [
            "european union", "europe", "eu only", "eu-only", "emea",
            "germany", "france", "netherlands", "spain", "italy",
            "poland", "sweden", "norway", "denmark", "finland",
            "belgium", "austria", "ireland", "portugal", "greece",
            "czech republic", "romania", "berlin", "amsterdam",
            "paris", "madrid", "rome", "stockholm", "dublin",
            "warsaw", "lisbon", "vienna", "munich", "barcelona",
        ],
    ),
    (
        "UK",
        [
            "united kingdom", "uk", "u.k.", "great britain", "england",
            "scotland", "wales", "london", "manchester", "birmingham",
            "edinburgh", "glasgow", "liverpool", "bristol", "cardiff",
        ],
    ),
    (
        "Canada",
        [
            "canada", "toronto", "vancouver", "montreal", "ontario",
            "british columbia", "quebec", "alberta", "calgary", "ottawa",
        ],
    ),
    (
        "India",
        [
            "india", "bangalore", "bengaluru", "hyderabad", "mumbai",
            "delhi", "chennai", "pune", "kolkata", "ahmedabad",
            "noida", "gurgaon", "gurugram",
        ],
    ),
    (
        "Brazil",
        [
            "brazil", "brasil", "são paulo", "sao paulo",
            "rio de janeiro", "belo horizonte", "salvador",
            "brasília", "brasilia", "fortaleza", "curitiba",
            "porto alegre", "recife",
        ],
    ),
    (
        "LatAm",
        [
            "latin america", "latam", "south america",
            "mexico", "argentina", "colombia", "chile", "peru",
            "venezuela", "ecuador", "uruguay", "paraguay", "bolivia",
            "guatemala", "costa rica", "panama", "dominican republic",
            "puerto rico", "buenos aires", "mexico city", "bogota",
            "santiago", "lima",
        ],
    ),
    (
        "Asia-Other",
        [
            # South Asia (excluding India, which has its own bucket)
            "pakistan", "bangladesh", "sri lanka", "nepal",
            "karachi", "lahore", "dhaka", "colombo",
            # Southeast Asia
            "philippines", "vietnam", "indonesia", "singapore",
            "thailand", "malaysia", "cambodia", "laos", "myanmar",
            "manila", "jakarta", "ho chi minh", "bangkok",
            "kuala lumpur",
            # East Asia
            "japan", "south korea", "china", "hong kong", "taiwan",
            "tokyo", "seoul", "shanghai", "beijing", "taipei",
        ],
    ),
    (
        "Africa",
        [
            "south africa", "nigeria", "kenya", "egypt", "morocco",
            "ghana", "tunisia", "algeria", "ethiopia", "tanzania",
            "uganda", "lagos", "nairobi", "cairo", "casablanca",
            "johannesburg", "cape town",
        ],
    ),
    (
        "Australia/NZ",
        [
            "australia", "new zealand", "sydney", "melbourne",
            "brisbane", "auckland", "wellington", "perth", "adelaide",
        ],
    ),
]


def _has_any(text: str, terms: Iterable[str]) -> bool:
    for term in terms:
        if term_pattern(term).search(text):
            return True
    return False


def normalize_location(
    raw: str | None, body: str | None = None
) -> str:
    """Bucket a job posting into one of the LOCATION_RULES categories.

    ``raw`` is the source-provided location string (may be None). If
    that's empty we fall back to scanning ``body``. First match wins.
    """
    candidates: list[str] = []
    if raw:
        candidates.append(str(raw))
    if body and not raw:
        # Only scan body when we have no raw location signal — the body
        # is full of location-ish noise (e.g. "California Bar exam") that
        # would over-match if we always merged it in.
        candidates.append(str(body))

    if not candidates:
        return "Unknown"

    text = " | ".join(candidates)
    for bucket, terms in LOCATION_RULES:
        if _has_any(text, terms):
            return bucket
    return "Unknown"
