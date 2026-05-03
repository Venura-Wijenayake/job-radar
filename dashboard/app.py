"""Job Radar — Streamlit dashboard MVP.

Two tabs:
  Today's Queue — sorted job list with score + matched terms +
    one-click status buttons (Interested / Applied / Skip / Hide).
  Pipeline — kanban grouped by tracking status with per-card
    notes editor and status mover.

Reads/writes through dashboard.data — no SQL or scoring logic in
this file.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path when launched via `streamlit run`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from dashboard.data import (  # noqa: E402
    PIPELINE_STATUSES,
    get_pipeline,
    get_profiles,
    get_stats,
    get_today_queue,
    set_status,
    update_notes,
)

PIPELINE_LABELS: dict[str, str] = {
    "interested": "💡 Interested",
    "applied": "📤 Applied",
    "phone_screen": "📞 Phone Screen",
    "interview": "💬 Interview",
    "offer": "🎉 Offer",
    "rejected": "❌ Rejected",
    "ghosted": "👻 Ghosted",
}


# ----- Helpers -----


def _score_badge(score: float) -> str:
    if score >= 75:
        return f":green-background[**{score:.0f}**]"
    if score >= 50:
        return f":yellow-background[**{score:.0f}**]"
    if score >= 25:
        return f":gray-background[**{score:.0f}**]"
    return f":red-background[**{score:.0f}**]"


def _fmt_date(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "?"


def _days_ago(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    delta = (datetime.now(timezone.utc).replace(tzinfo=None) - dt).days
    if delta <= 0:
        return "today"
    if delta == 1:
        return "1d ago"
    return f"{delta}d ago"


@st.cache_data(ttl=60)
def _cached_queue(profile_name: str) -> list[dict]:
    return get_today_queue(profile_name)


@st.cache_data(ttl=60)
def _cached_pipeline(profile_name: str) -> dict[str, list[dict]]:
    return get_pipeline(profile_name)


@st.cache_data(ttl=60)
def _cached_stats(profile_name: str) -> dict:
    return get_stats(profile_name)


@st.cache_data(ttl=300)
def _cached_profile_id(profile_name: str) -> int | None:
    for p in get_profiles():
        if p.name == profile_name:
            return p.id
    return None


def _invalidate_caches() -> None:
    st.cache_data.clear()


def _safe_set_status(item_id: int, profile_id: int, status: str, notes: str | None = None) -> bool:
    try:
        set_status(item_id, profile_id, status, notes=notes)
        _invalidate_caches()
        return True
    except Exception as exc:
        st.error(f"Failed to update status: {exc}")
        return False


def _safe_update_notes(item_id: int, profile_id: int, notes: str) -> bool:
    try:
        update_notes(item_id, profile_id, notes)
        _invalidate_caches()
        return True
    except Exception as exc:
        st.error(f"Failed to update notes: {exc}")
        return False


# ----- Page setup -----

st.set_page_config(
    page_title="Job Radar",
    page_icon="🎯",
    layout="wide",
)


# ----- Sidebar -----

with st.sidebar:
    st.title("🎯 Job Radar")
    st.caption("Daily job market intelligence")

    try:
        profiles = get_profiles()
    except Exception as exc:
        st.error(f"Failed to load profiles: {exc}")
        st.stop()

    if not profiles:
        st.warning(
            "No profiles found yet. Run:\n\n"
            "```\npython scripts/parse_resume.py "
            "data/resumes/your_resume.pdf your_profile_name\n```"
        )
        st.stop()

    profile_names = [p.name for p in profiles]
    if (
        "current_profile" not in st.session_state
        or st.session_state.current_profile not in profile_names
    ):
        st.session_state.current_profile = profile_names[0]

    selected = st.selectbox(
        "Profile",
        profile_names,
        index=profile_names.index(st.session_state.current_profile),
        key="profile_selector",
    )
    if selected != st.session_state.current_profile:
        st.session_state.current_profile = selected
        _invalidate_caches()
        st.rerun()

    if st.button("🔄 Refresh data", use_container_width=True):
        _invalidate_caches()
        st.rerun()

    st.divider()

    try:
        stats = _cached_stats(st.session_state.current_profile)
    except Exception as exc:
        st.error(f"Stats error: {exc}")
        stats = None

    if stats is not None:
        st.metric("Items scraped", stats["total_items"])
        st.metric("Items scored", stats["total_scored"])
        st.metric("Applied this week", stats["applications_this_week"])
        st.metric("Response rate", f"{stats['response_rate'] * 100:.0f}%")


profile_name: str = st.session_state.current_profile
profile_id = _cached_profile_id(profile_name)


# ----- Tabs -----

tab_queue, tab_pipeline = st.tabs(["📋 Today's Queue", "📊 Pipeline"])


# ----- Today's Queue -----

with tab_queue:
    try:
        queue = _cached_queue(profile_name)
    except Exception as exc:
        st.error(f"Failed to load queue: {exc}")
        queue = []

    fcol1, fcol2, fcol3 = st.columns([1, 2, 2])
    with fcol1:
        min_score = st.slider("Min score", 0, 100, 1, key="queue_min_score")
    sources_avail = sorted({i["source_name"] for i in queue}) or [""]
    with fcol2:
        selected_sources = st.multiselect(
            "Sources",
            sources_avail,
            default=sources_avail,
            key="queue_sources",
        )
    with fcol3:
        search = st.text_input(
            "Search title or company",
            "",
            key="queue_search",
            placeholder="e.g. analyst, python, acme",
        )

    filtered = [
        i
        for i in queue
        if i["score"] >= min_score
        and i["source_name"] in selected_sources
        and (
            not search
            or search.lower() in (i["title"] or "").lower()
            or search.lower() in (i["company"] or "").lower()
        )
    ]

    st.subheader(f"{len(filtered)} new opportunities")

    if not queue:
        st.info(
            "Nothing in the queue yet. Run the pipeline:\n\n"
            "```\npython scripts/run_scraper.py remoteok\n"
            f"python scripts/score_items.py {profile_name} --force\n```"
        )
    elif not filtered:
        st.info("No items match your current filters.")

    for item in filtered:
        with st.container(border=True):
            head_l, head_r = st.columns([1, 11])
            with head_l:
                st.markdown(_score_badge(item["score"]))
            with head_r:
                if item["url"]:
                    st.markdown(f"**[{item['title']}]({item['url']})**")
                else:
                    st.markdown(f"**{item['title']}**")
                meta_parts = [
                    p
                    for p in [
                        item["company"],
                        item["location"],
                        f"posted {_fmt_date(item['posted_at'])}",
                        item["source_name"],
                    ]
                    if p
                ]
                st.caption(" • ".join(meta_parts))

            if item["top_matched_terms"]:
                pills = " ".join(
                    f":gray-background[{t}]" for t in item["top_matched_terms"]
                )
                st.markdown(pills)

            btn_int, btn_app, btn_skip, btn_hide, _, status_col = st.columns(
                [1, 1, 1, 1, 1, 4]
            )
            base = f"q-{item['item_id']}"
            with btn_int:
                if st.button("Interested", key=f"{base}-int", use_container_width=True):
                    if _safe_set_status(item["item_id"], profile_id, "interested"):
                        st.rerun()
            with btn_app:
                if st.button("Applied", key=f"{base}-app", use_container_width=True):
                    if _safe_set_status(item["item_id"], profile_id, "applied"):
                        st.rerun()
            with btn_skip:
                if st.button("Skip", key=f"{base}-skip", use_container_width=True):
                    if _safe_set_status(item["item_id"], profile_id, "skipped"):
                        st.rerun()
            with btn_hide:
                if st.button("Hide", key=f"{base}-hide", use_container_width=True):
                    if _safe_set_status(item["item_id"], profile_id, "hidden"):
                        st.rerun()
            with status_col:
                if item["current_status"]:
                    label = PIPELINE_LABELS.get(
                        item["current_status"], item["current_status"]
                    )
                    st.markdown(f"<small>Status: {label}</small>", unsafe_allow_html=True)


# ----- Pipeline -----

with tab_pipeline:
    try:
        pipeline = _cached_pipeline(profile_name)
    except Exception as exc:
        st.error(f"Failed to load pipeline: {exc}")
        pipeline = {s: [] for s in PIPELINE_STATUSES}

    columns = st.columns(len(PIPELINE_STATUSES))
    for col, status_key in zip(columns, PIPELINE_STATUSES):
        items = pipeline.get(status_key, [])
        with col:
            st.markdown(f"**{PIPELINE_LABELS[status_key]}** ({len(items)})")
            if not items:
                st.caption("(empty)")
                continue
            for it in items:
                with st.container(border=True):
                    title = (it["title"] or "")[:70]
                    if it["url"]:
                        st.markdown(f"**[{title}]({it['url']})**")
                    else:
                        st.markdown(f"**{title}**")
                    if it["company"]:
                        st.caption(f"@ {it['company']}")
                    score_str = (
                        f"Score {it['score']:.0f}" if it["score"] is not None else "—"
                    )
                    extra = (
                        f" · applied {_days_ago(it['applied_at'])}"
                        if it["applied_at"]
                        else ""
                    )
                    st.caption(score_str + extra)

                    with st.expander("Edit"):
                        notes_key = f"p-notes-{it['item_id']}"
                        status_key_widget = f"p-status-{it['item_id']}"
                        save_key = f"p-save-{it['item_id']}"

                        new_notes = st.text_area(
                            "Notes",
                            value=it["notes"] or "",
                            key=notes_key,
                        )
                        new_status = st.selectbox(
                            "Move to",
                            PIPELINE_STATUSES,
                            index=PIPELINE_STATUSES.index(status_key),
                            format_func=lambda s: PIPELINE_LABELS[s],
                            key=status_key_widget,
                        )
                        if st.button("Save", key=save_key, use_container_width=True):
                            ok = _safe_set_status(
                                it["item_id"],
                                profile_id,
                                new_status,
                                notes=new_notes,
                            )
                            if ok:
                                st.rerun()
