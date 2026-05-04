from __future__ import annotations

from scoring.eligibility_utils import (
    detect_citizenship_required,
    detect_license_required,
)


# ----- citizenship -----


def test_citizenship_required_detects_must_be_us_citizen():
    assert detect_citizenship_required(
        "Applicants must be a US citizen to apply."
    )
    assert detect_citizenship_required("Must be US citizen.")
    assert detect_citizenship_required("US citizens only.")


def test_citizenship_required_inclusive_language_is_not_a_hit():
    """'US citizens, GCs, and visa holders welcome' is the OPPOSITE of
    restrictive — should not flag."""
    inclusive = (
        "We welcome US citizens, green-card holders, and visa holders. "
        "Our team is global."
    )
    assert detect_citizenship_required(inclusive) is False


def test_citizenship_required_detects_clearance_phrases():
    assert detect_citizenship_required("Active TS/SCI clearance required.")
    assert detect_citizenship_required("Top secret clearance is required.")
    assert detect_citizenship_required(
        "Must be able to obtain a public trust clearance."
    )


def test_citizenship_required_detects_no_sponsorship():
    assert detect_citizenship_required(
        "Note: we cannot sponsor employment-based visas at this time."
    )
    assert detect_citizenship_required("No sponsorship available.")
    assert detect_citizenship_required("We are unable to sponsor.")


def test_citizenship_required_handles_none_and_empty():
    assert detect_citizenship_required(None) is False
    assert detect_citizenship_required("") is False


def test_citizenship_required_irrelevant_text_is_false():
    assert (
        detect_citizenship_required(
            "We're a remote-first company hiring data analysts."
        )
        is False
    )


# ----- citizenship: inclusive override (Phase 4.6b) -----


def test_inclusive_override_us_citizen_or_permanent_resident():
    """Phase 4.6b regression case: 'Must be US citizen or permanent
    resident' welcomes PRs and should not flag the role as
    citizenship-required."""
    text = "Applicants must be US citizen or permanent resident."
    assert detect_citizenship_required(text) is False


def test_inclusive_override_authorized_to_work_in_us():
    text = (
        "You must be authorized to work in the US without sponsorship."
    )
    assert detect_citizenship_required(text) is False


def test_inclusive_override_no_visa_sponsorship_passes():
    """'No visa sponsorship' is treated as inclusive — GC holders
    don't need sponsorship."""
    text = (
        "Note: this role offers no visa sponsorship. PRs and citizens "
        "encouraged to apply."
    )
    assert detect_citizenship_required(text) is False


def test_restrictive_still_flagged_when_no_inclusive_present():
    """Regression: 'we cannot sponsor employment visas' alone (no
    inclusive language) still flags."""
    text = "Note: we cannot sponsor employment-based visas at this time."
    assert detect_citizenship_required(text) is True


def test_inclusive_override_does_not_unblock_clearance_required():
    """A clearance-required role can never be inclusive — TS/SCI
    holders are a small cleared population, not 'GC + citizen'."""
    text = (
        "Active TS/SCI clearance required. Open to US citizens or "
        "permanent residents who already hold clearance."
    )
    assert detect_citizenship_required(text) is True


def test_inclusive_phrasing_with_grammar_variations():
    text_a = (
        "We hire US citizens and lawful permanent residents only."
    )
    text_b = "Applicants must be authorized to work in the U.S."
    text_c = "U.S. citizen or permanent resident required."
    assert detect_citizenship_required(text_a) is False
    assert detect_citizenship_required(text_b) is False
    assert detect_citizenship_required(text_c) is False


# ----- license -----


def test_license_required_detects_drivers_license():
    assert detect_license_required(
        "Should have a valid driver's license required."
    )
    assert detect_license_required("Valid driver's license required.")
    assert detect_license_required("Must have valid drivers license.")


def test_license_required_detects_cdl():
    assert detect_license_required("CDL required.")
    assert detect_license_required("Commercial driver's license required.")


def test_license_required_detects_vehicle_requirement():
    assert detect_license_required("Personal vehicle required.")
    assert detect_license_required("Must have own vehicle.")
    assert detect_license_required("Reliable transportation required.")


def test_license_required_soft_phrasing_not_a_hit():
    """Aspirational / occasional phrasing should not flag."""
    assert (
        detect_license_required(
            "Willing to travel occasionally for client meetings."
        )
        is False
    )
    assert (
        detect_license_required("Some occasional driving may be involved.")
        is False
    )


def test_license_required_handles_none_and_empty():
    assert detect_license_required(None) is False
    assert detect_license_required("") is False
