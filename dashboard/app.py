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
from datetime import datetime, timedelta, timezone
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
    paginate,
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
from dashboard.queue_row import render_queue_row  # noqa: E402

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


# Per-page item count for the paginated queue. Round number that fits
# 1080p without scrolling under the compact-row layout.
PAGE_SIZE = 30
# Standard ceiling for the paginated queue (covers ~7 pages).
QUEUE_PAGE_CEILING = 200
# Hard ceiling for the "show all" mode — far above what any one user
# would scroll through, but still bounded so a runaway query can't
# pull the entire scored corpus into memory.
QUEUE_SHOW_ALL_CEILING = 5000


@st.cache_data(ttl=60)
def _cached_queue(profile_name: str, show_all: bool = False) -> list[dict]:
    # Fetch the broad set so client-side filter toggles can show/hide
    # applied + skipped without re-querying. Permanently-hidden rows
    # (Hide button, rejected, ghosted) stay out of the cache.
    # show_all=True bumps the ceiling well above the paginated case so
    # the user can browse the full ranked corpus.
    return get_today_queue(
        profile_name,
        exclude_statuses=["hidden", "rejected", "ghosted"],
        limit=QUEUE_SHOW_ALL_CEILING if show_all else QUEUE_PAGE_CEILING,
    )


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

POSTED_DATE_OPTIONS: dict[str, int | None] = {
    "Last 24h": 1,
    "Last 7 days": 7,
    "Last 30 days": 30,
    "All time": None,
}

GEO_TIER_OPTIONS = ["local", "regional", "domestic", "unknown", "foreign"]
GEO_TIER_DEFAULT = ["local", "regional", "domestic", "unknown"]
FIT_TIER_OPTIONS = ["high_fit", "stretch", "long_shot"]
FIT_TIER_LABELS = {
    "high_fit": "🎯 high fit",
    "stretch": "🎲 stretch",
    "long_shot": "🌙 long shot",
}


def _on_queue_status_change(
    item_id: int, profile_id: int | None, status: str
) -> None:
    """Click-handler used by render_queue_row. Persists the status,
    invalidates the queue cache, and re-runs the script."""
    if _safe_set_status(item_id, profile_id, status):
        st.rerun()


with tab_queue:
    with st.expander("Filters", expanded=False):
        row1 = st.columns([1, 2, 2])
        with row1[0]:
            min_score = st.slider("Min score", 0, 100, 1, key="queue_min_score")
        with row1[1]:
            search = st.text_input(
                "Search title or company",
                "",
                key="queue_search",
                placeholder="e.g. analyst, python, acme",
            )
        with row1[2]:
            posted_label = st.selectbox(
                "Posted",
                list(POSTED_DATE_OPTIONS.keys()),
                index=2,  # default = Last 30 days
                key="queue_posted_after",
            )
        posted_after_days = POSTED_DATE_OPTIONS[posted_label]

        row2 = st.columns([2, 2, 2])
        with row2[0]:
            selected_geo_tiers = st.multiselect(
                "Geo tier",
                GEO_TIER_OPTIONS,
                default=GEO_TIER_DEFAULT,
                key="queue_geo_tiers",
            )
        with row2[1]:
            selected_fit_tiers = st.multiselect(
                "Fit tier",
                FIT_TIER_OPTIONS,
                default=FIT_TIER_OPTIONS,
                format_func=lambda t: FIT_TIER_LABELS.get(t, t),
                key="queue_fit_tiers",
            )
        with row2[2]:
            # Sources is built from the queue itself — populated below.
            sources_placeholder = st.empty()

        row3 = st.columns([2, 2, 2])
        with row3[0]:
            hide_applied = st.toggle(
                "Hide already-applied", value=True, key="queue_hide_applied"
            )
        with row3[1]:
            hide_skipped = st.toggle(
                "Hide already-skipped", value=True, key="queue_hide_skipped"
            )
        with row3[2]:
            show_all = st.toggle(
                "Show all results",
                value=False,
                key="queue_show_all",
                help="Off = paginated 30-per-page (default). On = list "
                "all matches in one scroll.",
            )

    try:
        queue = _cached_queue(profile_name, show_all=show_all)
    except Exception as exc:
        st.error(f"Failed to load queue: {exc}")
        queue = []

    sources_avail = sorted({i["source_name"] for i in queue}) or [""]
    with sources_placeholder.container():
        selected_sources = st.multiselect(
            "Sources",
            sources_avail,
            default=sources_avail,
            key="queue_sources",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    posted_cutoff = (
        now - timedelta(days=posted_after_days)
        if posted_after_days is not None
        else None
    )

    def _passes_filters(it: dict) -> bool:
        if (it.get("score") or 0) < min_score:
            return False
        if it.get("source_name") not in selected_sources:
            return False
        if search:
            s = search.lower()
            if (
                s not in (it.get("title") or "").lower()
                and s not in (it.get("company") or "").lower()
            ):
                return False
        if (it.get("geo_tier") or "unknown") not in selected_geo_tiers:
            return False
        if (it.get("fit_tier") or "stretch") not in selected_fit_tiers:
            return False
        if posted_cutoff is not None:
            posted_at = it.get("posted_at")
            # NULL posted_at is kept (unknown != stale)
            if posted_at is not None and posted_at < posted_cutoff:
                return False
        if hide_applied and it.get("current_status") == "applied":
            return False
        if hide_skipped and it.get("current_status") == "skipped":
            return False
        return True

    filtered = [i for i in queue if _passes_filters(i)]

    tier_counts = {t: 0 for t in FIT_TIER_OPTIONS}
    for it in filtered:
        tier_counts[it.get("fit_tier") or "stretch"] = (
            tier_counts.get(it.get("fit_tier") or "stretch", 0) + 1
        )

    summary_bits = [
        f"{len(filtered)} opportunities",
        f"{FIT_TIER_LABELS['high_fit']} {tier_counts['high_fit']}",
        f"{FIT_TIER_LABELS['stretch']} {tier_counts['stretch']}",
        f"{FIT_TIER_LABELS['long_shot']} {tier_counts['long_shot']}",
    ]
    st.subheader(" • ".join(summary_bits))

    if not queue:
        st.info(
            "Nothing in the queue yet. Run the pipeline:\n\n"
            "```\npython scripts/run_scraper.py remoteok\n"
            f"python scripts/score_items.py {profile_name} --force\n```"
        )
    elif not filtered:
        st.info("No items match your current filters.")

    # Reset paginator to page 0 whenever any filter input changes —
    # otherwise narrowing the filter could leave the user stranded on
    # an out-of-range page. The filter signature is hashed into a
    # single key so we don't have to enumerate every input.
    filter_signature = (
        min_score,
        tuple(selected_sources),
        search,
        tuple(selected_geo_tiers),
        tuple(selected_fit_tiers),
        posted_after_days,
        hide_applied,
        hide_skipped,
        show_all,
    )
    if st.session_state.get("queue_filter_sig") != filter_signature:
        st.session_state["queue_filter_sig"] = filter_signature
        st.session_state["queue_page"] = 0

    current_page = int(st.session_state.get("queue_page", 0))
    visible, current_page, total_pages = paginate(
        filtered, PAGE_SIZE, current_page, show_all=show_all
    )
    st.session_state["queue_page"] = current_page

    for item in visible:
        render_queue_row(item, profile_id, _on_queue_status_change)

    # Page navigation. In show_all mode total_pages == 1 and the nav
    # collapses to a single label so it doesn't waste vertical space.
    if filtered and not show_all and total_pages > 1:
        nav_prev, nav_label, nav_next = st.columns([1, 6, 1])
        with nav_prev:
            if st.button(
                "◀ Prev",
                key="queue_prev",
                use_container_width=True,
                disabled=current_page <= 0,
            ):
                st.session_state["queue_page"] = max(0, current_page - 1)
                st.rerun()
        with nav_label:
            start = current_page * PAGE_SIZE + 1
            end = min((current_page + 1) * PAGE_SIZE, len(filtered))
            st.markdown(
                f"<div style='text-align:center'>Page {current_page + 1} "
                f"of {total_pages} &nbsp;·&nbsp; showing {start}–{end} "
                f"of {len(filtered)}</div>",
                unsafe_allow_html=True,
            )
        with nav_next:
            if st.button(
                "Next ▶",
                key="queue_next",
                use_container_width=True,
                disabled=current_page >= total_pages - 1,
            ):
                st.session_state["queue_page"] = min(
                    total_pages - 1, current_page + 1
                )
                st.rerun()
    elif filtered and show_all:
        st.caption(f"Showing all {len(filtered)} items")


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
