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
