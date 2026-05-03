"""Score a single Item against a single Profile.

Algorithm:
  - skill:    contribution = min(occurrences, 3) * weight
  - role:     contribution = 5 * weight if found anywhere; doubled if in title
  - keyword:  contribution = min(occurrences, 2) * weight
  - exclude:  contribution = -10 * weight if found
  - raw_score is summed across all criteria; floor 0
  - normalized = raw / theoretical_max * 100, capped at [0, 100]

The cleaned title and body text are computed in memory and not persisted.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Criterion, Item, Profile, Score

from .text_utils import clean_html, find_term_in_text, normalize_unicode


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _max_contribution(c: Criterion) -> float:
    """Per-criterion ceiling assuming maximum favorable input."""
    if c.kind == "skill":
        return 3 * c.weight
    if c.kind == "role":
        return 5 * c.weight * 2  # role + title boost
    if c.kind == "keyword":
        return 2 * c.weight
    return 0  # exclude only contributes negatively


def _theoretical_max(criteria: list[Criterion]) -> float:
    return float(sum(_max_contribution(c) for c in criteria))


def _contribution(c: Criterion, occurrences: int, in_title: bool) -> float:
    if occurrences == 0:
        if c.kind == "exclude":
            return 0.0
        return 0.0
    if c.kind == "skill":
        return float(min(occurrences, 3) * c.weight)
    if c.kind == "role":
        base = 5 * c.weight
        return float(base * 2 if in_title else base)
    if c.kind == "keyword":
        return float(min(occurrences, 2) * c.weight)
    if c.kind == "exclude":
        return float(-10 * c.weight)
    return 0.0


def score_item(item: Item, profile: Profile, session: Session) -> Score:
    title_clean = normalize_unicode(clean_html(item.title or ""))
    body_clean = normalize_unicode(clean_html(item.body or ""))

    criteria = (
        session.execute(
            select(Criterion).where(Criterion.profile_id == profile.id)
        )
        .scalars()
        .all()
    )

    raw_score = 0.0
    matched: list[dict] = []

    for c in criteria:
        title_offsets = find_term_in_text(c.term, title_clean)
        body_offsets = find_term_in_text(c.term, body_clean)
        occurrences = len(title_offsets) + len(body_offsets)
        in_title = bool(title_offsets)
        contribution = _contribution(c, occurrences, in_title)

        if contribution != 0:
            matched.append(
                {
                    "term": c.term,
                    "kind": c.kind,
                    "weight": c.weight,
                    "occurrences": occurrences,
                    "contribution": contribution,
                    "in_title": in_title,
                }
            )
            raw_score += contribution

    raw_score = max(0.0, raw_score)  # floor at 0

    max_possible = _theoretical_max(criteria)
    if max_possible > 0:
        normalized = (raw_score / max_possible) * 100
    else:
        normalized = 0.0
    normalized = max(0.0, min(100.0, normalized))

    existing = session.execute(
        select(Score).where(
            Score.item_id == item.id,
            Score.profile_id == profile.id,
        )
    ).scalar_one_or_none()

    now = _now_utc_naive()
    if existing is None:
        row = Score(
            item_id=item.id,
            profile_id=profile.id,
            score=normalized,
            matched_terms_json=matched,
            computed_at=now,
        )
        session.add(row)
        session.flush()
        return row

    existing.score = normalized
    existing.matched_terms_json = matched
    existing.computed_at = now
    session.flush()
    return existing
