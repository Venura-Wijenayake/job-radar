from __future__ import annotations

from sqlalchemy import inspect

from db.database import get_engine

EXPECTED_TABLES = {
    "sources",
    "profiles",
    "criteria",
    "items",
    "scores",
    "tracking",
    "keyword_extracts",
    "applications",
}


def test_init_creates_all_tables(fresh_db):
    insp = inspect(get_engine())
    tables = set(insp.get_table_names())
    assert EXPECTED_TABLES.issubset(tables), f"Missing: {EXPECTED_TABLES - tables}"


def test_items_has_expected_columns(fresh_db):
    insp = inspect(get_engine())
    cols = {c["name"] for c in insp.get_columns("items")}
    expected = {
        "id",
        "source_id",
        "external_id",
        "title",
        "body",
        "url",
        "metadata_json",
        "posted_at",
        "scraped_at",
        "content_hash",
    }
    assert expected.issubset(cols), f"Missing: {expected - cols}"


def test_items_unique_constraints(fresh_db):
    insp = inspect(get_engine())
    uniques = {
        tuple(sorted(u["column_names"])) for u in insp.get_unique_constraints("items")
    }
    assert ("external_id", "source_id") in uniques


def test_scores_unique_item_profile(fresh_db):
    insp = inspect(get_engine())
    uniques = {
        tuple(sorted(u["column_names"])) for u in insp.get_unique_constraints("scores")
    }
    assert ("item_id", "profile_id") in uniques


def test_criteria_has_profile_fk(fresh_db):
    insp = inspect(get_engine())
    fks = insp.get_foreign_keys("criteria")
    referred = {(fk["referred_table"], tuple(fk["referred_columns"])) for fk in fks}
    assert ("profiles", ("id",)) in referred
