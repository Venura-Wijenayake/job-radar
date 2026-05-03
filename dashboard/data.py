"""Data-access helpers for the Streamlit dashboard.

No Streamlit imports here — pure SQLAlchemy. The Streamlit layer in
dashboard/app.py imports these and renders the results. The pytest
suite tests these helpers directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from collections import Counter
from pathlib import Path

import yaml
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from db.database import get_session
from db.models import (
    Criterion,
    Item,
    KeywordExtract,
    Profile,
    Score,
    Source,
    Tracking,
    TrackingStatus,
)
from scoring.resume_parser import TAXONOMY_PATH, load_taxonomy
from scoring.text_utils import (
    clean_html,
    find_term_in_text,
    normalize_unicode,
    tokenize,
)

# Statuses hidden from the daily queue by default.
HIDDEN_FROM_QUEUE: list[str] = ["hidden", "skipped", "rejected", "ghosted"]

# Pipeline column order (left-to-right in the UI).
PIPELINE_STATUSES: list[str] = [
    "interested",
    "applied",
    "phone_screen",
    "interview",
    "offer",
    "rejected",
    "ghosted",
]


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _profile_by_name(session: Session, name: str) -> Optional[Profile]:
    return session.execute(
        select(Profile).where(Profile.name == name)
    ).scalar_one_or_none()


# ----- Profiles -----


def get_profiles() -> list[Profile]:
    """Return all profiles ordered by name. Used by the sidebar selector."""
    with get_session() as session:
        return list(
            session.execute(select(Profile).order_by(Profile.name)).scalars().all()
        )


# ----- Today's Queue -----


def get_today_queue(
    profile_name: str,
    limit: int = 50,
    exclude_statuses: Optional[list[str]] = None,
    collapse_duplicates: bool = True,
    allowed_locations: Optional[list[str]] = None,
    english_only: Optional[bool] = None,
    posted_after_days: Optional[int] = None,
    hide_citizenship_required: Optional[bool] = None,
    hide_license_required: Optional[bool] = None,
    hide_ghost_jobs_above: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Highest-scoring items for a profile, with the current tracking status
    inlined. Items with status in ``exclude_statuses`` are filtered out.

    When ``collapse_duplicates`` is True (the default), items sharing the
    same (lowercased title, lowercased company) are grouped and only the
    highest-scoring one is returned; the kept item carries the count of
    suppressed siblings on ``similar_count`` and their ids on
    ``similar_item_ids`` so a future "show all" UI can expand them.
    Items with empty/missing company are treated as unique and never
    grouped.

    Filters:
      ``allowed_locations`` — list of normalized-location buckets to keep.
        Items whose ``location_normalized`` is in the list OR is
        ``"Unknown"`` survive (lenient: don't hide ambiguous cases).
        When None, falls back to the profile's
        ``metadata_json["allowed_locations"]`` if present, otherwise no
        location filter is applied.
      ``english_only`` — when True, drops items whose
        ``language_detected`` is ``"other"``. ``"en"`` and ``"mixed"`` are
        kept. When None, falls back to the profile's
        ``metadata_json["english_only"]`` if present, otherwise False.
      ``posted_after_days`` — drops items whose ``posted_at`` is older
        than ``now - posted_after_days``. Items with NULL ``posted_at``
        are kept (an unknown date isn't grounds to call it stale).
        When None, falls back to the profile's
        ``metadata_json["posted_after_days"]`` if present, otherwise 30.
      ``hide_citizenship_required`` — when True, items whose
        ``metadata.citizenship_required`` is True are dropped. Falls
        back to profile metadata, default True.
      ``hide_license_required`` — same for ``license_required``.
      ``hide_ghost_jobs_above`` — items with ``ghost_score`` >= this
        threshold are dropped. Falls back to profile metadata, default
        80. Items with ghost_score in [50, threshold) survive but get
        ``ghost_warning=True`` set on the result dict.

    Filtering happens before duplicate-collapsing so the
    similar_count reflects only items that survived the filters.
    """
    if exclude_statuses is None:
        exclude_statuses = HIDDEN_FROM_QUEUE

    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return []

        # Resolve filter defaults from profile metadata when not given explicitly.
        profile_meta = profile.metadata_json or {}
        if allowed_locations is None:
            allowed_locations = profile_meta.get("allowed_locations")
        if english_only is None:
            english_only = bool(profile_meta.get("english_only", False))
        if posted_after_days is None:
            posted_after_days = int(profile_meta.get("posted_after_days", 30))
        if hide_citizenship_required is None:
            hide_citizenship_required = bool(
                profile_meta.get("hide_citizenship_required", True)
            )
        if hide_license_required is None:
            hide_license_required = bool(
                profile_meta.get("hide_license_required", True)
            )
        if hide_ghost_jobs_above is None:
            hide_ghost_jobs_above = int(
                profile_meta.get("hide_ghost_jobs_above", 80)
            )

        # Geo-tier display boosts (Phase 4.1) — soft re-rank, never persisted.
        boost_by_tier = {
            "local": int(profile_meta.get("geo_boost_local", 20)),
            "regional": int(profile_meta.get("geo_boost_regional", 10)),
            "domestic": int(profile_meta.get("geo_boost_domestic", 0)),
            "unknown": 0,
        }

        excluded_enums = [TrackingStatus(s) for s in exclude_statuses]
        excluded_item_ids = (
            select(Tracking.item_id)
            .where(Tracking.profile_id == profile.id)
            .where(Tracking.status.in_(excluded_enums))
        )

        recency_cutoff = _now_utc_naive() - timedelta(days=posted_after_days)

        # Fetch a wider slice so the geo-boost re-rank can pull local
        # items up from below the limit's natural score cutoff.
        sql_limit = max(limit * 3, 200)

        rows = session.execute(
            select(Score, Item, Source, Tracking)
            .join(Item, Score.item_id == Item.id)
            .join(Source, Item.source_id == Source.id)
            .outerjoin(
                Tracking,
                and_(
                    Tracking.item_id == Item.id,
                    Tracking.profile_id == profile.id,
                ),
            )
            .where(Score.profile_id == profile.id)
            .where(Item.id.notin_(excluded_item_ids))
            .where(
                or_(Item.posted_at >= recency_cutoff, Item.posted_at.is_(None))
            )
            .order_by(Score.score.desc(), Item.posted_at.desc())
            .limit(sql_limit)
        ).all()

        result: list[dict[str, Any]] = []
        for score, item, source, tracking in rows:
            md = item.metadata_json or {}

            location_norm = md.get("location_normalized") or "Unknown"
            language_det = md.get("language_detected") or "en"

            if allowed_locations is not None:
                if location_norm not in allowed_locations and location_norm != "Unknown":
                    continue
            if english_only and language_det == "other":
                continue

            citizenship_req = bool(md.get("citizenship_required", False))
            license_req = bool(md.get("license_required", False))
            ghost_score = int(md.get("ghost_score") or 0)

            if hide_citizenship_required and citizenship_req:
                continue
            if hide_license_required and license_req:
                continue
            if ghost_score >= hide_ghost_jobs_above:
                continue

            ghost_warning = 50 <= ghost_score < hide_ghost_jobs_above

            geo_tier = md.get("geo_tier") or "unknown"
            geo_boost = boost_by_tier.get(geo_tier, 0)
            score_value = score.score or 0.0
            display_score = score_value + geo_boost

            top_three = sorted(
                score.matched_terms_json or [],
                key=lambda t: t.get("contribution", 0),
                reverse=True,
            )[:3]
            result.append(
                {
                    "item_id": item.id,
                    "title": item.title,
                    "company": md.get("company"),
                    "location": md.get("location"),
                    "location_normalized": location_norm,
                    "language_detected": language_det,
                    "posted_at": item.posted_at,
                    "scraped_at": item.scraped_at,
                    "source_name": source.name,
                    "url": item.url,
                    "score": score.score,
                    "raw_score": score.raw_score,
                    "top_matched_terms": [t["term"] for t in top_three],
                    "current_status": (
                        tracking.status.value if tracking is not None else None
                    ),
                    "current_notes": tracking.notes if tracking is not None else None,
                    "citizenship_required": citizenship_req,
                    "license_required": license_req,
                    "ghost_score": ghost_score,
                    "ghost_warning": ghost_warning,
                    "geo_tier": geo_tier,
                    "geo_boost_applied": geo_boost,
                    "display_score": display_score,
                    "similar_count": 0,
                    "similar_item_ids": [],
                }
            )

        if not collapse_duplicates:
            result.sort(
                key=lambda x: (
                    -(x.get("display_score") or 0),
                    -(x["posted_at"].timestamp() if x["posted_at"] else 0),
                )
            )
            return result[:limit]

        # Group by (title, company); items with empty company stay unique.
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in result:
            title_norm = (entry["title"] or "").strip().lower()
            company_norm = (entry["company"] or "").strip().lower()
            if not company_norm:
                key = ("__unique__", f"id_{entry['item_id']}")
            else:
                key = (title_norm, company_norm)

            if key in grouped:
                grouped[key]["similar_count"] += 1
                grouped[key]["similar_item_ids"].append(entry["item_id"])
            else:
                grouped[key] = entry

        # Sort by display_score (= raw score + geo boost) so local items
        # bubble up. SQL pre-ordered by raw score; we re-sort here on the
        # boosted value and trim to the caller's requested limit.
        deduped = list(grouped.values())
        deduped.sort(
            key=lambda x: (
                -(x.get("display_score") or 0),
                -(x["posted_at"].timestamp() if x["posted_at"] else 0),
            )
        )
        return deduped[:limit]


# ----- Pipeline -----


def get_pipeline(profile_name: str) -> dict[str, list[dict[str, Any]]]:
    """Tracked items grouped by status. Statuses with no items return [].
    Items within each status are ordered by last_status_change_at DESC.
    """
    result: dict[str, list[dict[str, Any]]] = {s: [] for s in PIPELINE_STATUSES}

    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return result

        rows = session.execute(
            select(Tracking, Item, Score)
            .join(Item, Tracking.item_id == Item.id)
            .outerjoin(
                Score,
                and_(
                    Score.item_id == Item.id,
                    Score.profile_id == profile.id,
                ),
            )
            .where(Tracking.profile_id == profile.id)
            .order_by(Tracking.last_status_change_at.desc())
        ).all()

        for tracking, item, score in rows:
            md = item.metadata_json or {}
            status_val = tracking.status.value
            if status_val not in result:
                continue  # unknown status — skip silently
            result[status_val].append(
                {
                    "item_id": item.id,
                    "title": item.title,
                    "company": md.get("company"),
                    "url": item.url,
                    "score": score.score if score is not None else None,
                    "applied_at": tracking.applied_at,
                    "last_status_change_at": tracking.last_status_change_at,
                    "notes": tracking.notes,
                }
            )

        return result


# ----- Tracking writes -----


def set_status(
    item_id: int,
    profile_id: int,
    status: str,
    notes: Optional[str] = None,
) -> Tracking:
    """Upsert the tracking row for (item_id, profile_id).

    - Always updates last_status_change_at.
    - On the first transition into "applied", stamps applied_at to now;
      subsequent calls with status="applied" leave applied_at untouched.
    - If `notes` is provided, replaces the notes field; if None, leaves
      existing notes alone.
    """
    status_enum = TrackingStatus(status)
    now = _now_utc_naive()

    with get_session() as session:
        existing = session.execute(
            select(Tracking).where(
                Tracking.item_id == item_id,
                Tracking.profile_id == profile_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            row = Tracking(
                item_id=item_id,
                profile_id=profile_id,
                status=status_enum,
                notes=notes,
                last_status_change_at=now,
                applied_at=now if status_enum == TrackingStatus.applied else None,
            )
            session.add(row)
        else:
            existing.status = status_enum
            existing.last_status_change_at = now
            if notes is not None:
                existing.notes = notes
            if (
                status_enum == TrackingStatus.applied
                and existing.applied_at is None
            ):
                existing.applied_at = now
            row = existing

        session.commit()
        session.refresh(row)
        return row


def update_notes(item_id: int, profile_id: int, notes: str) -> Tracking:
    """Update only the notes field. If no tracking row exists yet, create
    one with status="interested"."""
    now = _now_utc_naive()

    with get_session() as session:
        existing = session.execute(
            select(Tracking).where(
                Tracking.item_id == item_id,
                Tracking.profile_id == profile_id,
            )
        ).scalar_one_or_none()

        if existing is None:
            row = Tracking(
                item_id=item_id,
                profile_id=profile_id,
                status=TrackingStatus.interested,
                notes=notes,
                last_status_change_at=now,
            )
            session.add(row)
        else:
            existing.notes = notes
            row = existing

        session.commit()
        session.refresh(row)
        return row


# ----- Stats -----


def get_stats(profile_name: str) -> dict[str, Any]:
    """Sidebar stats: counts plus a 7-day-application total and a response
    rate.  response_rate = (phone_screen + interview + offer) / applied,
    using the count of tracking rows currently in those statuses. If
    `applied` count is 0, response_rate is 0.0 (no division by zero).
    """
    empty: dict[str, Any] = {
        "total_items": 0,
        "total_scored": 0,
        "total_tracked": 0,
        "by_status": {},
        "applications_this_week": 0,
        "response_rate": 0.0,
    }

    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return empty

        total_items = session.execute(
            select(func.count(Item.id))
        ).scalar_one()
        total_scored = session.execute(
            select(func.count(Score.id)).where(Score.profile_id == profile.id)
        ).scalar_one()
        total_tracked = session.execute(
            select(func.count(Tracking.id)).where(Tracking.profile_id == profile.id)
        ).scalar_one()

        by_status_rows = session.execute(
            select(Tracking.status, func.count(Tracking.id))
            .where(Tracking.profile_id == profile.id)
            .group_by(Tracking.status)
        ).all()
        by_status: dict[str, int] = {row[0].value: row[1] for row in by_status_rows}

        seven_days_ago = _now_utc_naive() - timedelta(days=7)
        applications_this_week = session.execute(
            select(func.count(Tracking.id))
            .where(Tracking.profile_id == profile.id)
            .where(Tracking.applied_at >= seven_days_ago)
        ).scalar_one()

        applied = by_status.get("applied", 0)
        responses = (
            by_status.get("phone_screen", 0)
            + by_status.get("interview", 0)
            + by_status.get("offer", 0)
        )
        response_rate = responses / applied if applied > 0 else 0.0

        return {
            "total_items": total_items,
            "total_scored": total_scored,
            "total_tracked": total_tracked,
            "by_status": by_status,
            "applications_this_week": applications_this_week,
            "response_rate": response_rate,
        }


# ----- Resume Tailor -----

# Template phrasings for common skills/concepts. Used in suggested_rewrites
# when a JD keyword is buried or missing from the resume. Resume-tailor
# users can edit these in config later — for now they live in code.
EXAMPLE_PHRASING: dict[str, str] = {
    "tableau": "Built interactive Tableau dashboards visualizing X data for Y stakeholders",
    "power bi": "Developed Power BI reports tracking [metric] across [audience]",
    "looker": "Built LookML models surfacing [domain] metrics in Looker dashboards",
    "snowflake": "Wrote optimized Snowflake SQL queries on [N]+ row tables for [purpose]",
    "bigquery": "Wrote BigQuery SQL with windowing functions for [analysis type]",
    "redshift": "Optimized Redshift query performance via distribution keys and sort keys",
    "postgresql": "Designed PostgreSQL schemas with appropriate indexing for OLTP workloads",
    "mysql": "Tuned MySQL queries and indexes for [N]+ QPS analytics workloads",
    "mongodb": "Modeled MongoDB collections for [domain] document workloads",
    "airflow": "Authored Airflow DAGs orchestrating [N] daily ETL pipelines",
    "dbt": "Developed dbt models with version-controlled transformations and tests",
    "spark": "Processed [N]GB datasets with PySpark transformations",
    "aws": "Deployed analytics workflows on AWS (S3, Lambda, Athena)",
    "azure": "Used Azure Data Factory for ETL orchestration",
    "gcp": "Built BigQuery models for analytical workloads on GCP",
    "r": "Used R for statistical modeling and exploratory analysis",
    "spss": "Performed statistical analysis using SPSS for [study type]",
    "tensorflow": "Built TensorFlow models for [classification/regression task]",
    "pytorch": "Developed PyTorch deep learning pipelines for [domain]",
    "kubernetes": "Deployed analytics services on Kubernetes for scalable processing",
    "docker": "Containerized analytical workflows with Docker for reproducible environments",
    "git": "Managed version control with Git including feature branches and code reviews",
    "ci/cd": "Set up CI/CD pipelines for automated data validation and deployment",
    "etl": "Designed ETL pipelines processing [N]M rows daily across [N] sources",
    "warehouse": "Modeled data warehouse schemas using star/snowflake patterns",
    "a/b testing": "Designed A/B tests measuring [metric] with statistical significance testing",
    "regression": "Applied linear/logistic regression for [prediction task]",
    "classification": "Built classification models for [target] prediction",
    "clustering": "Used K-means clustering to segment [N] customers into actionable groups",
    "time series": "Performed time-series forecasting using ARIMA/Prophet for [metric]",
    "stakeholder": "Translated stakeholder requirements into measurable analytical deliverables",
    "executive": "Presented analytical findings to executive leadership with clear narratives",
    "agile": "Worked in agile sprints with cross-functional product teams",
    "kpi": "Defined and reported KPIs aligned with [business goal]",
}

_GENERIC_PHRASING = (
    "Consider adding a bullet that demonstrates your experience with {term}"
)


def _generate_example_phrasing(term: str) -> str:
    """Return the template phrasing for ``term`` or a generic fallback."""
    key = (term or "").lower().strip()
    return EXAMPLE_PHRASING.get(key, _GENERIC_PHRASING.format(term=term))


def _term_resume_count(term: str, resume_tokens: list[str], resume_text: str) -> int:
    """Count how many times ``term`` appears in the resume.

    Single-word terms use a token Counter (fast); multi-word and special-char
    terms (a/b testing, c++, power bi) fall back to find_term_in_text.
    """
    key = term.lower().strip()
    if " " in key or any(c in key for c in "+#/"):
        return len(find_term_in_text(term, resume_text))
    return resume_tokens.count(key)


def get_resume_tailor_view(
    item_id: int, profile_name: str
) -> dict[str, Any]:
    """Build the diff view for one item against a profile's resume."""
    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return {}

        item = session.execute(
            select(Item).where(Item.id == item_id)
        ).scalar_one_or_none()
        if item is None:
            return {}

        kw_extract = session.execute(
            select(KeywordExtract).where(KeywordExtract.item_id == item_id)
        ).scalar_one_or_none()
        jd_keywords_raw = list(kw_extract.keywords_json or []) if kw_extract else []

        criteria = (
            session.execute(
                select(Criterion).where(Criterion.profile_id == profile.id)
            )
            .scalars()
            .all()
        )

        score_row = session.execute(
            select(Score).where(
                Score.item_id == item_id,
                Score.profile_id == profile.id,
            )
        ).scalar_one_or_none()
        score_value = score_row.score if score_row else 0.0

        md = item.metadata_json or {}

        item_dict = {
            "item_id": item.id,
            "title": item.title,
            "company": md.get("company"),
            "url": item.url,
            "body_cleaned": clean_html(item.body or ""),
            "location_normalized": md.get("location_normalized") or "Unknown",
            "score": score_value,
        }

        # Taxonomy lookup so the UI can flag in_taxonomy badges.
        try:
            tax = load_taxonomy()
        except Exception:
            tax = {}
        taxonomy_terms: set[str] = set()
        for cat in (tax.get("skills") or {}).values():
            taxonomy_terms.update(t.lower() for t in cat)
        taxonomy_terms.update((t or "").lower() for t in (tax.get("roles") or []))
        taxonomy_terms.update((t or "").lower() for t in (tax.get("keywords") or []))

        jd_keywords: list[dict] = []
        for kw in jd_keywords_raw:
            jd_keywords.append(
                {
                    **kw,
                    "in_taxonomy": kw.get("term", "").lower() in taxonomy_terms,
                }
            )

        resume_criteria = [
            {
                "id": c.id,
                "term": c.term,
                "weight": c.weight,
                "kind": c.kind,
                "source": c.source,
            }
            for c in criteria
        ]
        criteria_terms_lower = {c.term.lower() for c in criteria}

        resume_text_raw = profile.resume_raw_text or ""
        resume_text = normalize_unicode(resume_text_raw)
        resume_tokens = tokenize(resume_text)

        have_strong: list[dict] = []
        have_buried: list[dict] = []
        missing: list[dict] = []

        for kw in jd_keywords:
            term = kw.get("term", "")
            if not term:
                continue
            if term.lower() in criteria_terms_lower:
                count = _term_resume_count(term, resume_tokens, resume_text)
                enriched = {**kw, "resume_frequency": count}
                if count >= 2:
                    have_strong.append(enriched)
                else:
                    have_buried.append(enriched)
            else:
                missing.append(kw)

        missing.sort(
            key=lambda x: x.get("frequency", 0) * x.get("importance", 1.0),
            reverse=True,
        )
        missing = missing[:10]

        suggested_rewrites: list[dict] = []
        for kw in have_buried:
            suggested_rewrites.append(
                {
                    "term": kw["term"],
                    "category": "buried",
                    "example_phrasing": _generate_example_phrasing(kw["term"]),
                }
            )
        for kw in missing[:5]:
            suggested_rewrites.append(
                {
                    "term": kw["term"],
                    "category": "missing",
                    "example_phrasing": _generate_example_phrasing(kw["term"]),
                }
            )

        return {
            "item": item_dict,
            "jd_keywords": jd_keywords,
            "resume_criteria": resume_criteria,
            "diff": {
                "have_strong": have_strong,
                "have_buried": have_buried,
                "missing": missing,
            },
            "suggested_rewrites": suggested_rewrites,
        }


# ----- Settings -----


def add_manual_criterion(
    profile_name: str, term: str, kind: str, weight: int
) -> Criterion | None:
    """Idempotently insert a kind/term tuple as source="manual".
    Returns the row, or None if (term, kind) already exists for the profile.
    """
    if not term:
        raise ValueError("term cannot be empty")
    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            raise ValueError(f"Profile not found: {profile_name!r}")
        existing = session.execute(
            select(Criterion).where(
                Criterion.profile_id == profile.id,
                Criterion.term == term,
                Criterion.kind == kind,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return None
        row = Criterion(
            profile_id=profile.id,
            term=term,
            kind=kind,
            weight=weight,
            match_type="fuzzy",
            source="manual",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def remove_manual_criterion(profile_name: str, criterion_id: int) -> bool:
    """Delete a criterion. Refuses to delete rows where source != "manual"."""
    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return False
        row = session.execute(
            select(Criterion).where(
                Criterion.id == criterion_id,
                Criterion.profile_id == profile.id,
            )
        ).scalar_one_or_none()
        if row is None or row.source != "manual":
            return False
        session.delete(row)
        session.commit()
        return True


def list_manual_criteria(profile_name: str) -> list[dict]:
    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return []
        rows = (
            session.execute(
                select(Criterion).where(
                    Criterion.profile_id == profile.id,
                    Criterion.source == "manual",
                )
            )
            .scalars()
            .all()
        )
        return [
            {"id": r.id, "term": r.term, "kind": r.kind, "weight": r.weight}
            for r in rows
        ]


def list_taxonomy(taxonomy_path: Path | str = TAXONOMY_PATH) -> dict:
    with open(taxonomy_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_profile_summary(profile_name: str) -> dict:
    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return {}
        kind_counts = session.execute(
            select(Criterion.kind, func.count(Criterion.id))
            .where(Criterion.profile_id == profile.id)
            .group_by(Criterion.kind)
        ).all()
        counts = {kind: n for kind, n in kind_counts}
        meta = profile.metadata_json or {}
        return {
            "name": profile.name,
            "resume_filename": profile.resume_filename,
            "parsed_at": profile.parsed_at,
            "criteria_counts_by_kind": counts,
            "filter_config": {
                "allowed_locations": meta.get("allowed_locations"),
                "english_only": meta.get("english_only"),
                "posted_after_days": meta.get("posted_after_days"),
            },
        }
