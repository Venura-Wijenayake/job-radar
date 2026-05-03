"""Data-access helpers for the Streamlit dashboard.

No Streamlit imports here — pure SQLAlchemy. The Streamlit layer in
dashboard/app.py imports these and renders the results. The pytest
suite tests these helpers directly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from db.database import get_session
from db.models import (
    Item,
    Profile,
    Score,
    Source,
    Tracking,
    TrackingStatus,
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
) -> list[dict[str, Any]]:
    """Highest-scoring items for a profile, with the current tracking status
    inlined. Items with status in ``exclude_statuses`` are filtered out.

    When ``collapse_duplicates`` is True (the default), items sharing the
    same (lowercased title, lowercased company) are grouped and only the
    highest-scoring one is returned; the kept item carries the count of
    suppressed siblings on ``similar_count`` and their ids on
    ``similar_item_ids`` so a future "show all" UI can expand them.
    Items with empty/missing company are treated as unique and never
    grouped — different one-person companies posting to the same job
    title shouldn't be collapsed.
    """
    if exclude_statuses is None:
        exclude_statuses = HIDDEN_FROM_QUEUE

    with get_session() as session:
        profile = _profile_by_name(session, profile_name)
        if profile is None:
            return []

        excluded_enums = [TrackingStatus(s) for s in exclude_statuses]
        excluded_item_ids = (
            select(Tracking.item_id)
            .where(Tracking.profile_id == profile.id)
            .where(Tracking.status.in_(excluded_enums))
        )

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
            .order_by(Score.score.desc(), Item.posted_at.desc())
            .limit(limit)
        ).all()

        result: list[dict[str, Any]] = []
        for score, item, source, tracking in rows:
            md = item.metadata_json or {}
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
                    "similar_count": 0,
                    "similar_item_ids": [],
                }
            )

        if not collapse_duplicates:
            return result

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

        # SQL ordering preserved by dict insertion order; re-sort defensively
        # in case the highest-scoring per group needs to bubble up.
        deduped = list(grouped.values())
        deduped.sort(
            key=lambda x: (
                -(x["score"] or 0),
                -(x["posted_at"].timestamp() if x["posted_at"] else 0),
            )
        )
        return deduped


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
