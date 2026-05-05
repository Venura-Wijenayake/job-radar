from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "company_boards.yaml"
)


def _load() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def test_config_file_exists():
    assert CONFIG_PATH.exists()


def test_yaml_loads():
    data = _load()
    assert isinstance(data, dict)


def test_both_keys_present():
    data = _load()
    assert "greenhouse" in data
    assert "lever" in data


def test_greenhouse_slugs_are_non_empty_strings():
    data = _load()
    slugs = data.get("greenhouse") or []
    assert len(slugs) > 0
    for slug in slugs:
        assert isinstance(slug, str)
        assert slug.strip() == slug
        assert len(slug) > 0


def test_lever_slugs_are_non_empty_strings():
    data = _load()
    slugs = data.get("lever") or []
    assert len(slugs) > 0
    for slug in slugs:
        assert isinstance(slug, str)
        assert slug.strip() == slug
        assert len(slug) > 0


def test_no_duplicate_greenhouse_slugs():
    data = _load()
    slugs = data.get("greenhouse") or []
    assert len(slugs) == len(set(slugs))


def test_no_duplicate_lever_slugs():
    data = _load()
    slugs = data.get("lever") or []
    assert len(slugs) == len(set(slugs))


def test_ashby_section_exists_and_has_validated_slugs():
    """Phase 4.8c re-curation: each slug in the YAML was probed against
    the public job board API and confirmed to return a non-empty jobs
    list. Threshold lowered from the Phase 4.6a hand-picked baseline
    of 30 because validation churned out ~16 dead slugs (anthropic,
    huggingface, characterai, replicate, …) — keeping them would
    inflate the count without adding inventory."""
    data = _load()
    assert "ashby" in data
    slugs = data.get("ashby") or []
    assert len(slugs) >= 25


def test_ashby_slugs_have_no_duplicates_after_additions():
    """Phase 4.8c added 10 new vector-DB / ML-infra slugs. The merged
    list must remain duplicate-free."""
    data = _load()
    slugs = data.get("ashby") or []
    assert len(slugs) == len(set(slugs))


def test_ashby_slugs_are_lowercase_strings():
    data = _load()
    slugs = data.get("ashby") or []
    for slug in slugs:
        assert isinstance(slug, str)
        assert slug == slug.lower(), f"slug not lowercase: {slug!r}"
        assert slug.strip() == slug
        assert len(slug) > 0


def test_no_duplicate_ashby_slugs():
    data = _load()
    slugs = data.get("ashby") or []
    assert len(slugs) == len(set(slugs))


def test_workable_section_exists_with_validated_slugs():
    """Phase 4.8c re-curation: of 64 candidate Workable slugs probed
    (current + Phase 4.8c suggestions), only 1 returned a non-empty
    jobs list. Most "famous" Workable customers (datadog, deel, ramp,
    miro, gusto, plaid, mercury) keep stub Workable accounts but no
    longer post via the public widget API. The threshold drops from
    25 to 1 — the realistic outcome of the re-curation."""
    data = _load()
    assert "workable" in data
    slugs = data.get("workable") or []
    assert len(slugs) >= 1


def test_workable_slugs_are_validated_recent():
    """Sentinel: the workmotion slug is the only confirmed-active
    Workable board as of the Phase 4.8c re-curation. If this drops
    out, run validate_workable_slugs.py and refresh."""
    data = _load()
    slugs = data.get("workable") or []
    assert "workmotion" in slugs


def test_workable_slugs_are_lowercase_strings():
    data = _load()
    slugs = data.get("workable") or []
    for slug in slugs:
        assert isinstance(slug, str)
        assert slug == slug.lower(), f"slug not lowercase: {slug!r}"
        assert slug.strip() == slug
        assert len(slug) > 0


def test_no_duplicate_workable_slugs():
    data = _load()
    slugs = data.get("workable") or []
    assert len(slugs) == len(set(slugs))
