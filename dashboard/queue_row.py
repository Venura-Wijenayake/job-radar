"""Compact row component for Today's Queue.

Renders one queue item as a single bordered container occupying ~4 lines:

  [SCORE] Title — company • location 📍tier  🎯 fit-tier
  ✅ python  ✅ sql  ✅ analytics    ❌ tableau  ❌ snowflake  ❌ dbt
  posted 2d ago • Greenhouse                       Status: 💡 Interested
  [Interested] [Applied] [Skip] [Hide]            ▸ Details

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

# Per-source visual badge. Streamlit's :color-background[] palette is
# fixed at {blue, green, orange, red, violet, gray, yellow, rainbow}
# — assignments below are tuned so the most-used sources get the
# distinct/punchier colors and no two sources collide. Add new
# sources here when adding scrapers.
SOURCE_BADGES: dict[str, tuple[str, str]] = {
    "Adzuna": ("🟦", "blue"),
    "Greenhouse": ("🟩", "green"),
    "Lever": ("🟧", "orange"),
    "Ashby": ("🟪", "violet"),
    "RemoteOK": ("🟫", "red"),
    "Remotive": ("⬜", "gray"),
    "WeWorkRemotely": ("⬛", "rainbow"),
    "HackerNewsWhoIsHiring": ("🟨", "yellow"),
}


def _source_badge(name: str | None) -> str:
    if not name:
        return ""
    emoji, color = SOURCE_BADGES.get(name, ("📡", "gray"))
    return f":{color}-background[{emoji} {name}]"


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
    """Color-coded score badge, banded as: >=80 green, 50-79 amber, <50 muted."""
    if score >= 80:
        return f":green-background[**{score:.0f}**]"
    if score >= 50:
        return f":orange-background[**{score:.0f}**]"
    return f":gray-background[**{score:.0f}**]"


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


def _format_breakdown(b: dict) -> str:
    """Render land_score_breakdown as a fixed-width text block.

    Each line shows one multiplier and the human-readable reason that
    produced it. The leading values are right-aligned so multipliers
    eyeball-align cleanly when scanning a Details panel.
    """
    matched_terms = b.get("skills_matched_terms") or []
    matched_summary = (
        ", ".join(matched_terms[:5])
        + (f" (+{len(matched_terms) - 5} more)" if len(matched_terms) > 5 else "")
    ) or "none"

    lines = [
        f"Match score:           {b.get('match_score', 0):>6.1f}",
        f"x Skill density:       {b.get('skill_density_bonus', 0):+.2%}    "
        f"matched: {matched_summary}",
        f"x Source quality:      x{b.get('source_quality_mult', 1.0):.2f}",
        f"x Title family:        x{b.get('title_family_mult', 1.0):.2f}    "
        f"({b.get('title_family_matched', 'default')})",
        f"x Experience match:    x{b.get('experience_match_mult', 1.0):.2f}",
        f"x Salary band:         x{b.get('salary_mult', 1.0):.2f}    "
        f"({b.get('salary_reason', '')})",
        f"x Eligibility:         x{b.get('eligibility_mult', 1.0):.2f}"
        + (
            f"    (blocked: {b['eligibility_reason']})"
            if b.get("eligibility_reason")
            else ""
        ),
        f"= Land score:          {b.get('land_score', 0):>6.1f}",
    ]
    return "\n".join(lines)


def render_queue_row(
    item: dict,
    profile_id: Optional[int],
    on_status_change: Callable[[int, Optional[int], str], None],
) -> None:
    """Render a single queue row. ~4 lines tall by design."""
    with st.container(border=True):
        # Row 1 — score on the left, title + meta + tier badges on the right.
        col_score, col_title = st.columns([1, 8])
        with col_score:
            # Phase 4.6b: land_score is the primary badge — sort key
            # and the user-facing "how landable is this" number.
            primary_score = (
                item.get("land_score")
                or item.get("display_score")
                or item.get("score")
                or 0
            )
            st.markdown(_score_badge(primary_score))
        with col_title:
            badges = ""
            similar = item.get("similar_count", 0) or 0
            if similar > 0:
                badges += f" :gray-background[+{similar} similar]"
            if item.get("ghost_warning"):
                badges += " :orange-background[⚠️ might be ghost]"
            geo_badge = GEO_TIER_BADGES.get(item.get("geo_tier") or "unknown", "")
            fit_badge = FIT_TIER_BADGES.get(item.get("fit_tier") or "stretch", "")
            source_badge = _source_badge(item.get("source_name"))
            tier_badges = " ".join(
                b for b in (source_badge, geo_badge, fit_badge) if b
            )

            title = item.get("title") or ""
            url = item.get("url")
            link = f"[{title}]({url})" if url else title
            st.markdown(f"**{link}**{badges} &nbsp; {tier_badges}")

            # Source moves into the badge row; meta caption keeps
            # company/location/posted-age only.
            meta_parts = [
                p
                for p in [
                    item.get("company"),
                    item.get("location"),
                    f"posted {_days_ago(item.get('posted_at'))}",
                ]
                if p
            ]
            current_status = item.get("current_status")
            status_suffix = ""
            if current_status:
                label = PIPELINE_LABELS.get(current_status, current_status)
                status_suffix = f" • status: {label}"
            st.caption(" • ".join(meta_parts) + status_suffix)

        # Row 2 — pros + cons chips on a single line. The two short
        # column layout keeps them aligned visually rather than the
        # markdown wrapping the full chip line.
        chips: list[str] = []
        for term in (item.get("top_strong") or [])[:3]:
            chips.append(f":green-background[✅ {_truncate(term, 18)}]")
        for term in (item.get("top_missing") or [])[:3]:
            chips.append(f":red-background[❌ {_truncate(term, 18)}]")
        if chips:
            st.markdown(" &nbsp; ".join(chips))

        # Row 3 — four equal-width action buttons + a click-to-expand
        # details panel on the same row. use_container_width keeps
        # the buttons compact without truncating the labels.
        btn_int, btn_app, btn_skip, btn_hide = st.columns(4)
        base = f"q-{item['item_id']}"
        with btn_int:
            if st.button("Interested", key=f"{base}-int", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "interested")
        with btn_app:
            if st.button("Applied", key=f"{base}-app", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "applied")
        with btn_skip:
            if st.button("Skip", key=f"{base}-skip", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "skipped")
        with btn_hide:
            if st.button("Hide", key=f"{base}-hide", use_container_width=True):
                on_status_change(item["item_id"], profile_id, "hidden")

        with st.expander("Details", expanded=False):
            breakdown = item.get("land_score_breakdown") or {}
            if breakdown:
                st.markdown("**Why this score?**")
                st.code(_format_breakdown(breakdown), language="text")
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
