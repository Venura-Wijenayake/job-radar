"""Compact row component for Today's Queue.

Renders one queue item as a single bordered container with:
  Row 1 — score badge, fit-tier badge, geo-tier badge, title, company,
          location, posted-age, source.
  Row 2 — pros chips (top 3 strong) + cons chips (top 3 missing).
  Row 3 — action buttons (Interested / Applied / Skip / Hide) and an
          expander revealing the full body excerpt + matched terms.

All Streamlit-native primitives — no custom HTML/JS.

The ``on_status_change`` callback is invoked with
``(item_id, profile_id, status)`` when the user clicks one of the
action buttons. Callers wire this up to ``set_status`` (with the
caches invalidated and a rerun triggered).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

import streamlit as st


# Human-friendly fit-tier badges. Streamlit's :color-background[]
# directive supports a fixed palette — we use green/orange/gray.
FIT_TIER_BADGES: dict[str, str] = {
    "high_fit": ":green-background[🎯 high fit]",
    "stretch": ":orange-background[🎲 stretch]",
    "long_shot": ":gray-background[🌙 long shot]",
}

GEO_TIER_BADGES: dict[str, str] = {
    "local": ":green-background[📍 local]",
    "regional": ":blue-background[📍 regional]",
    "domestic": ":violet-background[📍 domestic]",
    "foreign": ":red-background[📍 foreign]",
    "unknown": "",
}

PIPELINE_LABELS: dict[str, str] = {
    "interested": "💡 Interested",
    "applied": "📤 Applied",
    "phone_screen": "📞 Phone Screen",
    "interview": "💬 Interview",
    "offer": "🎉 Offer",
    "rejected": "❌ Rejected",
    "ghosted": "👻 Ghosted",
    "skipped": "⏭️ Skipped",
    "hidden": "🙈 Hidden",
}


def _score_badge(score: float) -> str:
    if score >= 75:
        return f":green-background[**{score:.0f}**]"
    if score >= 50:
        return f":orange-background[**{score:.0f}**]"
    if score >= 25:
        return f":gray-background[**{score:.0f}**]"
    return f":red-background[**{score:.0f}**]"


def _days_ago(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    delta = (datetime.now(timezone.utc).replace(tzinfo=None) - dt).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "1d ago"
    return f"{delta}d ago"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def render_queue_row(
    item: dict,
    profile_id: Optional[int],
    on_status_change: Callable[[int, Optional[int], str], None],
) -> None:
    """Render a single queue row. ``on_status_change`` runs on button click."""
    with st.container(border=True):
        col_meta, col_main, col_actions = st.columns([1, 6, 2])

        with col_meta:
            display_score = item.get("display_score") or item.get("score") or 0
            st.markdown(_score_badge(display_score))
            tier = item.get("fit_tier") or "stretch"
            st.markdown(FIT_TIER_BADGES.get(tier, tier))
            geo_badge = GEO_TIER_BADGES.get(item.get("geo_tier") or "unknown", "")
            if geo_badge:
                st.markdown(geo_badge)

        with col_main:
            similar = item.get("similar_count", 0) or 0
            badges = ""
            if similar > 0:
                badges += f" :gray-background[+{similar} similar]"
            if item.get("ghost_warning"):
                badges += " :orange-background[⚠️ might be ghost]"
            title = item.get("title") or ""
            url = item.get("url")
            if url:
                st.markdown(f"**[{title}]({url})**{badges}")
            else:
                st.markdown(f"**{title}**{badges}")

            meta_parts = [
                p
                for p in [
                    item.get("company"),
                    item.get("location"),
                    f"posted {_days_ago(item.get('posted_at'))}",
                    item.get("source_name"),
                ]
                if p
            ]
            st.caption(" • ".join(meta_parts))

            chips: list[str] = []
            for term in (item.get("top_strong") or [])[:3]:
                chips.append(f":green-background[✅ {_truncate(term, 18)}]")
            for term in (item.get("top_missing") or [])[:3]:
                chips.append(f":red-background[❌ {_truncate(term, 18)}]")
            if chips:
                st.markdown(" ".join(chips))

            current_status = item.get("current_status")
            if current_status:
                label = PIPELINE_LABELS.get(current_status, current_status)
                st.caption(f"Status: {label}")

        with col_actions:
            base = f"q-{item['item_id']}"
            if st.button("Interested", key=f"{base}-int", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "interested")
            if st.button("Applied", key=f"{base}-app", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "applied")
            if st.button("Skip", key=f"{base}-skip", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "skipped")
            if st.button("Hide", key=f"{base}-hide", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "hidden")

        with st.expander("Details"):
            top_terms = item.get("top_matched_terms") or []
            if top_terms:
                st.markdown(
                    "**Matched terms:** "
                    + " ".join(f":gray-background[{t}]" for t in top_terms)
                )
            ghost = item.get("ghost_score")
            if ghost is not None:
                st.caption(f"Ghost score: {ghost} / 100")
            body = (item.get("body") or "").strip()
            if body:
                excerpt = body[:1200]
                if len(body) > 1200:
                    excerpt += " …"
                st.text(excerpt)
