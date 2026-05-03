from __future__ import annotations

from scoring.location_utils import normalize_location


def test_normalize_location_us_states():
    assert normalize_location("Sacramento, CA") == "US"
    assert normalize_location("Austin, Texas") == "US"
    assert normalize_location("New York, NY") == "US"
    assert normalize_location("United States") == "US"


def test_normalize_location_brazil():
    assert normalize_location("Belo Horizonte ou Salvador") == "Brazil"
    assert normalize_location("São Paulo, Brasil") == "Brazil"
    assert normalize_location("Rio de Janeiro") == "Brazil"


def test_normalize_location_remote_us_specific():
    assert normalize_location("Remote (US only)") == "Remote-US"
    assert normalize_location("Remote, US") == "Remote-US"
    assert normalize_location("US-only remote") == "Remote-US"


def test_normalize_location_remote_global():
    assert normalize_location("Remote") == "Remote-Global"
    assert normalize_location("Worldwide") == "Remote-Global"
    assert normalize_location("Anywhere") == "Remote-Global"
    assert normalize_location("Fully remote") == "Remote-Global"


def test_normalize_location_unknown_fallback():
    assert normalize_location("xyz random gibberish") == "Unknown"
    assert normalize_location("") == "Unknown"
    assert normalize_location(None) == "Unknown"


def test_normalize_location_uk():
    assert normalize_location("London, UK") == "UK"
    assert normalize_location("Manchester, England") == "UK"


def test_normalize_location_canada():
    assert normalize_location("Toronto, Ontario") == "Canada"
    assert normalize_location("Vancouver, BC") == "Canada"


def test_normalize_location_india():
    assert normalize_location("Bangalore") == "India"
    assert normalize_location("Hyderabad, India") == "India"


def test_normalize_location_eu():
    assert normalize_location("Berlin, Germany") == "EU"
    assert normalize_location("Amsterdam") == "EU"


def test_normalize_location_pakistan():
    assert normalize_location("Rawalpindi, Pakistan") == "Asia-Other"
    assert normalize_location("Karachi") == "Asia-Other"
    assert normalize_location("Lahore, Pakistan") == "Asia-Other"


def test_normalize_location_japan():
    assert normalize_location("Tokyo, Japan") == "Asia-Other"
    assert normalize_location("Japan") == "Asia-Other"


def test_normalize_location_south_asia_extras():
    assert normalize_location("Dhaka, Bangladesh") == "Asia-Other"
    assert normalize_location("Colombo, Sri Lanka") == "Asia-Other"
    assert normalize_location("Kathmandu, Nepal") == "Asia-Other"


def test_state_code_does_not_match_inside_words():
    """'CA' as a state code shouldn't match inside 'Canada' or 'capital'."""
    assert normalize_location("Canada") == "Canada"
    assert normalize_location("capital city") != "US"


def test_remote_us_takes_priority_over_remote_global():
    """A post that is both 'remote' AND 'US-only' should bucket as Remote-US."""
    assert normalize_location("Remote, US only") == "Remote-US"
