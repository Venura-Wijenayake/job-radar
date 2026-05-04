from __future__ import annotations

from scoring.location_utils import classify_geo_tier, normalize_location


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


# ----- classify_geo_tier -----


def test_classify_geo_tier_sacramento():
    assert classify_geo_tier("Sacramento, CA") == "local"
    assert classify_geo_tier("Roseville, CA") == "local"
    assert classify_geo_tier("Folsom") == "local"


def test_classify_geo_tier_bay_area():
    assert classify_geo_tier("San Francisco, CA") == "regional"
    assert classify_geo_tier("San Jose") == "regional"
    assert classify_geo_tier("Bay Area") == "regional"


def test_classify_geo_tier_remote():
    """Remote-anywhere is considered 'local' for daily ranking purposes —
    the user can take it from home so it shouldn't lose to another local
    item that happens to mention a Sacramento city."""
    assert classify_geo_tier("Remote") == "local"
    assert classify_geo_tier("Remote (Worldwide)") == "local"


def test_classify_geo_tier_texas():
    """Texas is in-country but not in the configured CA + West Coast
    region, so it should bucket as domestic."""
    assert classify_geo_tier("Austin, Texas") == "domestic"
    assert classify_geo_tier("Houston") == "domestic"


def test_classify_geo_tier_oregon():
    assert classify_geo_tier("Portland, Oregon") == "regional"
    assert classify_geo_tier("Seattle, Washington State") == "regional"


def test_classify_geo_tier_unknown():
    assert classify_geo_tier(None) == "unknown"
    assert classify_geo_tier("") == "unknown"
    assert classify_geo_tier("xyz random gibberish") == "unknown"


def test_classify_geo_tier_respects_home_region_disabled():
    """When home_region is empty, the 'remote->local' shortcut shouldn't
    fire — Remote-Global still falls through to 'domestic' via the
    normalize_location bucket, but it's no longer 'local'."""
    assert classify_geo_tier("Remote", home_region="") == "domestic"


def test_state_code_does_not_match_inside_words():
    """'CA' as a state code shouldn't match inside 'Canada' or 'capital'."""
    assert normalize_location("Canada") == "Canada"
    assert normalize_location("capital city") != "US"


def test_remote_us_takes_priority_over_remote_global():
    """A post that is both 'remote' AND 'US-only' should bucket as Remote-US."""
    assert normalize_location("Remote, US only") == "Remote-US"


# ----- classify_geo_tier: foreign bucket (Phase 4.2.1) -----


def test_classify_geo_tier_dublin_is_foreign():
    assert classify_geo_tier("Dublin, Ireland") == "foreign"


def test_classify_geo_tier_bengaluru_is_foreign():
    assert classify_geo_tier("Bengaluru") == "foreign"
    assert classify_geo_tier("Bangalore, India") == "foreign"


def test_classify_geo_tier_eu_uk_canada_brazil_etc_are_foreign():
    assert classify_geo_tier("Berlin, Germany") == "foreign"
    assert classify_geo_tier("London, UK") == "foreign"
    assert classify_geo_tier("Toronto, Ontario") == "foreign"
    assert classify_geo_tier("São Paulo") == "foreign"
    assert classify_geo_tier("Mexico City") == "foreign"
    assert classify_geo_tier("Tokyo, Japan") == "foreign"
    assert classify_geo_tier("Sydney, Australia") == "foreign"


def test_classify_geo_tier_toronto_remote_is_foreign_not_local():
    """The bug fix: 'Toronto, Remote in Canada' must NOT fall into 'local'
    via the remote-anywhere shortcut. Foreign signal beats remote."""
    assert classify_geo_tier("Toronto, Remote in Canada") == "foreign"
    assert classify_geo_tier("Remote — Canada") == "foreign"
    assert classify_geo_tier("Bengaluru / Remote") == "foreign"


def test_classify_geo_tier_us_remote_still_local():
    """Regression: bare 'Remote' (no foreign signal) is still local."""
    assert classify_geo_tier("Remote") == "local"
    assert classify_geo_tier("Remote, Worldwide") == "local"
    # The remote-anywhere shortcut still wins for Remote-US buckets too,
    # which is what we want — a US-only remote post is fine from Sacramento.
    assert classify_geo_tier("Remote (US)") == "local"


def test_classify_geo_tier_us_locations_unaffected():
    """Regression: US locations classify the same as before the foreign change."""
    assert classify_geo_tier("Sacramento, CA") == "local"
    assert classify_geo_tier("San Francisco") == "regional"
    assert classify_geo_tier("Austin, Texas") == "domestic"
