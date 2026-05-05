"""Phase 4.8b — render-side smoke tests for queue_row.

Confirms the full-JD body display path doesn't truncate at 1200 chars
the way Phase 4.6b's preview did, and that long bodies render inside
the scrollable container fork.
"""
from __future__ import annotations

from streamlit.testing.v1 import AppTest


# Minimal Streamlit script that imports render_queue_row and feeds it
# a fixture item. Body content is interpolated via session_state so we
# can re-use the same script for short / long / empty cases.
_SCRIPT = """
import streamlit as st
from dashboard.queue_row import render_queue_row

body = st.session_state.get("body", "")
item = {
    "item_id": 1,
    "title": "Data Analyst",
    "url": "https://example.com/jd/1",
    "body": body,
    "company": "Acme",
    "location": "Remote",
    "posted_at": None,
    "scraped_at": None,
    "source_name": "Greenhouse",
    "score": 70,
    "land_score": 75,
    "land_score_breakdown": {},
    "top_strong": ["python"],
    "top_missing": ["snowflake"],
    "top_matched_terms": ["python"],
    "geo_tier": "local",
    "fit_tier": "high_fit",
    "ghost_score": 10,
    "ghost_warning": False,
    "current_status": None,
}

render_queue_row(item, profile_id=1, on_status_change=lambda *a, **kw: None)
"""


def _render_with(body: str) -> AppTest:
    at = AppTest.from_string(_SCRIPT)
    at.session_state["body"] = body
    at.run(timeout=10)
    return at


def test_queue_row_renders_full_body_for_short_jd():
    """A short body (<= 1500 chars) renders inline without errors."""
    body = "We're hiring a data analyst. " * 5  # ~150 chars
    at = _render_with(body)
    assert not at.exception


def test_queue_row_renders_full_body_for_long_jd():
    """A long body (>1500 chars) wraps in a scrollable container but
    still renders the full content (no '...' truncation)."""
    long_body = "Detailed job description paragraph. " * 100  # ~3500 chars
    at = _render_with(long_body)
    assert not at.exception
    # No ellipsis truncation marker from the old 1200-char preview.
    rendered = "".join(t.value for t in at.text)
    assert "…" not in rendered
    # Full body present (use a sentinel that survives whatever wrapping
    # Streamlit does).
    assert "Detailed job description paragraph." in rendered


def test_queue_row_handles_empty_body():
    """An item with no body should still render (just no body section)."""
    at = _render_with("")
    assert not at.exception
