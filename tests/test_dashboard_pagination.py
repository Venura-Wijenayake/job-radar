"""Tests for dashboard.data.paginate — the pure helper that powers
the queue's prev/next navigation. Streamlit isn't involved; these
tests run against the slicing logic alone."""
from __future__ import annotations

import pytest

from dashboard.data import paginate


def test_pagination_slices_correctly_for_page_size_30():
    """100 items, page size 30: page 0 → 30, page 3 → 10 leftover."""
    items = list(range(100))
    visible, page, total_pages = paginate(items, page_size=30, page=0)
    assert visible == list(range(30))
    assert page == 0
    assert total_pages == 4

    visible, page, total_pages = paginate(items, page_size=30, page=3)
    assert visible == list(range(90, 100))
    assert page == 3
    assert total_pages == 4


def test_show_all_returns_full_filtered_list():
    items = list(range(120))
    visible, page, total_pages = paginate(
        items, page_size=30, page=2, show_all=True
    )
    assert visible == items
    assert page == 0
    assert total_pages == 1


def test_pagination_clamps_out_of_range_page():
    """Filter narrows from 100 → 25 items but session_state says page=3.
    paginate must clamp to the last valid page rather than returning
    an empty slice."""
    items = list(range(25))
    visible, page, total_pages = paginate(items, page_size=30, page=3)
    assert visible == items  # only one page exists
    assert page == 0
    assert total_pages == 1


def test_pagination_handles_empty_list():
    visible, page, total_pages = paginate([], page_size=30, page=0)
    assert visible == []
    assert page == 0
    assert total_pages == 1


def test_pagination_total_pages_rounds_up():
    """A list of 31 items at page_size 30 yields 2 pages, not 1."""
    items = list(range(31))
    _, _, total_pages = paginate(items, page_size=30, page=0)
    assert total_pages == 2


def test_pagination_negative_page_clamps_to_zero():
    items = list(range(60))
    visible, page, total_pages = paginate(items, page_size=30, page=-5)
    assert visible == list(range(30))
    assert page == 0
    assert total_pages == 2
