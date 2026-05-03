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

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from dashboard.data import (  # noqa: E402
    PIPELINE_STATUSES,
    add_manual_criterion,
    get_pipeline,
    get_profile_summary,
    get_profiles,
    get_resume_tailor_view,
    get_stats,
    get_today_queue,
    list_manual_criteria,
    list_taxonomy,
    remove_manual_criterion,
    set_status,
    update_notes,
)
from dashboard.insights import (  # noqa: E402
    market_summary,
    posting_velocity_by_day,
    skill_demand_frequency,
    source_breakdown,
    top_hiring_companies,
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
    # Streamlit's :color-background[] directive only supports a fixed set of
    # color names — as of 1.40.2 the valid list is
    # [blue, green, orange, red, violet, gray, grey, rainbow]. "yellow" is
    # not recognized, so use "orange" for the 50-74 range.
    if score >= 75:
        return f":green-background[**{score:.0f}**]"
    if score >= 50:
        return f":orange-background[**{score:.0f}**]"
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

tab_queue, tab_pipeline, tab_tailor, tab_insights, tab_settings = st.tabs(
    [
        "📋 Today's Queue",
        "📊 Pipeline",
        "✂️ Resume Tailor",
        "📈 Market Insights",
        "⚙️ Settings",
    ]
)


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
                similar = item.get("similar_count", 0)
                badges = ""
                if similar > 0:
                    badges += f" :gray-background[+{similar} similar]"
                if item.get("ghost_warning"):
                    badges += " :orange-background[⚠️ might be ghost listing]"
                if item["url"]:
                    st.markdown(
                        f"**[{item['title']}]({item['url']})**{badges}"
                    )
                else:
                    st.markdown(f"**{item['title']}**{badges}")
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

                geo_tier = item.get("geo_tier")
                if geo_tier == "local":
                    st.markdown(":green-background[📍 local]")
                elif geo_tier == "regional":
                    st.markdown(":blue-background[📍 regional]")

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


# ----- Resume Tailor -----

with tab_tailor:
    try:
        queue_for_tailor = _cached_queue(profile_name)
    except Exception as exc:
        st.error(f"Failed to load items: {exc}")
        queue_for_tailor = []

    if not queue_for_tailor:
        st.info("Score some items first (run scripts/score_items.py).")
    else:
        # Top 20 by score
        top20 = queue_for_tailor[:20]
        options: dict[str, int] = {}
        for q in top20:
            label = (
                f"[{q['score']:.0f}] {(q['title'] or '')[:55]} "
                f"@ {(q['company'] or '?')[:25]}"
            )
            options[label] = q["item_id"]

        selected_label = st.selectbox(
            "Pick an item to tailor your resume for",
            list(options.keys()),
            index=0,
            key="tailor_select",
        )
        selected_id = options[selected_label]

        try:
            view = get_resume_tailor_view(selected_id, profile_name)
        except Exception as exc:
            st.error(f"Failed to build tailor view: {exc}")
            view = {}

        if view:
            it = view["item"]
            st.markdown(
                f"### [{it['title']}]({it['url']})"
                if it.get("url")
                else f"### {it['title']}"
            )
            st.caption(
                f"{it.get('company') or '?'} • "
                f"{it.get('location_normalized') or 'Unknown'} • "
                f"score {it.get('score', 0):.1f}"
            )

            diff = view["diff"]
            col_strong, col_buried, col_missing = st.columns(3)
            with col_strong:
                st.markdown(f"### ✅ Strong matches ({len(diff['have_strong'])})")
                st.caption("Mentioned ≥ 2× in your resume")
                if not diff["have_strong"]:
                    st.write("_None._")
                for kw in diff["have_strong"]:
                    st.markdown(
                        f":green-background[{kw['term']}] "
                        f"_(×{kw['resume_frequency']})_"
                    )
            with col_buried:
                st.markdown(f"### ⚠️ Buried in resume ({len(diff['have_buried'])})")
                st.caption("Listed but not emphasized — consider amplifying")
                if not diff["have_buried"]:
                    st.write("_None._")
                for kw in diff["have_buried"]:
                    st.markdown(
                        f":orange-background[{kw['term']}] "
                        f"_(×{kw['resume_frequency']})_"
                    )
            with col_missing:
                st.markdown(f"### ❌ Missing skills ({len(diff['missing'])})")
                st.caption("Top JD keywords not on your resume")
                if not diff["missing"]:
                    st.write("_None._")
                for kw in diff["missing"]:
                    st.markdown(f":red-background[{kw['term']}]")

            suggestions = view["suggested_rewrites"]
            if suggestions:
                with st.expander(
                    f"Suggested rewrites ({len(suggestions)})", expanded=True
                ):
                    for rw in suggestions:
                        with st.container(border=True):
                            badge = (
                                ":orange-background[buried]"
                                if rw["category"] == "buried"
                                else ":red-background[missing]"
                            )
                            st.markdown(f"**{rw['term']}** &nbsp; {badge}")
                            st.write(rw["example_phrasing"])


# ----- Market Insights -----


@st.cache_data(ttl=300)
def _cached_market_summary() -> dict:
    return market_summary()


@st.cache_data(ttl=300)
def _cached_top_hiring(limit: int) -> list[dict]:
    return top_hiring_companies(limit)


@st.cache_data(ttl=300)
def _cached_skill_demand(taxonomy_path: str, top_n: int) -> list[dict]:
    return skill_demand_frequency(taxonomy_path, top_n)


@st.cache_data(ttl=300)
def _cached_velocity(days: int) -> list[dict]:
    return posting_velocity_by_day(days)


@st.cache_data(ttl=300)
def _cached_source_breakdown() -> list[dict]:
    return source_breakdown()


with tab_insights:
    try:
        summary = _cached_market_summary()
    except Exception as exc:
        st.error(f"Failed to load market summary: {exc}")
        summary = {
            "total_items": 0,
            "total_companies": 0,
            "freshest_posted_at": None,
        }

    m1, m2, m3 = st.columns(3)
    m1.metric("Total items", summary["total_items"])
    m2.metric("Companies hiring", summary["total_companies"])
    freshest = summary.get("freshest_posted_at")
    m3.metric(
        "Freshest posting",
        freshest.strftime("%Y-%m-%d") if freshest else "—",
    )

    row1_l, row1_r = st.columns(2)
    with row1_l:
        st.subheader("Top hiring companies")
        try:
            data = _cached_top_hiring(15)
            if data:
                df = pd.DataFrame(data)
                fig = px.bar(
                    df,
                    x="count",
                    y="company",
                    orientation="h",
                    template="plotly_dark",
                )
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No items yet.")
        except Exception as exc:
            st.error(f"Failed: {exc}")
    with row1_r:
        st.subheader("Skill demand (taxonomy ∩ JDs)")
        try:
            data = _cached_skill_demand("config/skills_taxonomy.yaml", 20)
            if data:
                df = pd.DataFrame(data)
                fig = px.bar(
                    df,
                    x="item_count",
                    y="skill",
                    orientation="h",
                    template="plotly_dark",
                )
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No keyword extracts yet — run scripts/extract_keywords.py.")
        except Exception as exc:
            st.error(f"Failed: {exc}")

    row2_l, row2_r = st.columns(2)
    with row2_l:
        st.subheader("Posting velocity (last 30 days)")
        try:
            data = _cached_velocity(30)
            if data:
                df = pd.DataFrame(data)
                fig = px.line(
                    df, x="date", y="count", template="plotly_dark", markers=True
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No dated postings in the last 30 days.")
        except Exception as exc:
            st.error(f"Failed: {exc}")
    with row2_r:
        st.subheader("Source breakdown")
        try:
            data = _cached_source_breakdown()
            if data:
                df = pd.DataFrame(data)
                fig = px.pie(
                    df,
                    values="count",
                    names="source_name",
                    template="plotly_dark",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No items yet.")
        except Exception as exc:
            st.error(f"Failed: {exc}")


# ----- Settings -----


def _rescore_after_criteria_change(prof_name: str) -> None:
    """Run a force-rescore so the new/removed manual criterion is
    reflected in the queue immediately. Imported here so the heavy
    scoring deps load lazily."""
    from scoring.batch import score_all_items

    with st.spinner("Re-scoring queue..."):
        score_all_items(prof_name, force=True)
    _invalidate_caches()


with tab_settings:
    st.subheader("Profile")
    try:
        summary_data = get_profile_summary(profile_name)
    except Exception as exc:
        st.error(f"Failed to load profile summary: {exc}")
        summary_data = {}

    if summary_data:
        info_cols = st.columns(2)
        with info_cols[0]:
            st.write(f"**Name:** {summary_data['name']}")
            st.write(
                f"**Resume:** {summary_data.get('resume_filename') or '_none_'}"
            )
            parsed = summary_data.get("parsed_at")
            st.write(
                f"**Parsed:** {parsed.strftime('%Y-%m-%d %H:%M') if parsed else '_never_'}"
            )
        with info_cols[1]:
            counts = summary_data.get("criteria_counts_by_kind", {})
            for kind in ("skill", "role", "keyword", "exclude"):
                st.write(f"**{kind} criteria:** {counts.get(kind, 0)}")
        with st.expander("Filter config"):
            st.json(summary_data.get("filter_config", {}))

    st.divider()

    st.subheader("Manual criteria")
    st.caption(
        "Manually-added rows. Resume-extracted criteria are not editable here "
        "(re-parse the resume to refresh those)."
    )

    try:
        manual_rows = list_manual_criteria(profile_name)
    except Exception as exc:
        st.error(f"Failed to load manual criteria: {exc}")
        manual_rows = []

    if not manual_rows:
        st.write("_None yet._")
    else:
        for row in manual_rows:
            row_cols = st.columns([2, 1, 1, 1])
            row_cols[0].write(f"**{row['term']}**")
            row_cols[1].write(row["kind"])
            row_cols[2].write(f"weight {row['weight']}")
            if row_cols[3].button("Remove", key=f"rm-{row['id']}"):
                try:
                    if remove_manual_criterion(profile_name, row["id"]):
                        _rescore_after_criteria_change(profile_name)
                        st.success(f"Removed '{row['term']}'.")
                        st.rerun()
                    else:
                        st.error("Could not remove (not a manual row?).")
                except Exception as exc:
                    st.error(f"Remove failed: {exc}")

    with st.form("add_manual_criterion", clear_on_submit=True):
        st.write("**Add a criterion**")
        form_cols = st.columns([3, 2, 2])
        with form_cols[0]:
            new_term = st.text_input(
                "Term", placeholder="e.g. tableau, healthcare, finance"
            )
        with form_cols[1]:
            new_kind = st.selectbox(
                "Kind", ["skill", "keyword", "exclude"], index=0
            )
        with form_cols[2]:
            new_weight = st.slider("Weight", min_value=1, max_value=5, value=3)
        if st.form_submit_button("Add criterion"):
            if not new_term.strip():
                st.warning("Term cannot be empty.")
            else:
                try:
                    added = add_manual_criterion(
                        profile_name,
                        new_term.strip().lower(),
                        new_kind,
                        new_weight,
                    )
                    if added is None:
                        st.warning(
                            f"'{new_term}' ({new_kind}) already exists."
                        )
                    else:
                        _rescore_after_criteria_change(profile_name)
                        st.success(
                            f"Added '{new_term}' ({new_kind}, w={new_weight}). "
                            "Queue re-scored."
                        )
                        st.rerun()
                except Exception as exc:
                    st.error(f"Add failed: {exc}")

    st.divider()

    st.subheader("Skills taxonomy (read-only)")
    st.caption("Edit `config/skills_taxonomy.yaml` and re-parse to change.")
    try:
        st.json(list_taxonomy())
    except Exception as exc:
        st.error(f"Failed to load taxonomy: {exc}")
