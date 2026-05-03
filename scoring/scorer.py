"""Score a single Item against a single Profile.

Per-criterion contributions:
  - skill:    min(occurrences, 3) * weight
  - role:     8 * weight if found anywhere; doubled (16 * weight) if
              the role term appears in the item title. The 8x base
              (up from the original 5x) makes role matches more
              decisive without overwhelming the skill signal.
  - keyword:  min(occurrences, 2) * weight
  - exclude:  -10 * weight if found

Public API:
  score_item_raw(item, profile, session, criteria=None)
      -> (raw_score, matched_terms): pure computation, no persistence.

  score_item(item, profile, session) -> Score: persists a Score row.
      The `score` field uses theoretical-max normalization for backwards
      compatibility with single-item callers; batch.score_all_items
      overrides it with dataset-relative normalization.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Criterion, Item, Profile, Score

from .text_utils import clean_html, find_term_in_text, normalize_unicode

# Multipliers — bumped from 5 to 8 in Phase 2.5 to make role hits more
# decisive in the final ranking.
ROLE_BASE_MULT = 8
ROLE_TITLE_BOOST = 2
SKILL_OCC_CAP = 3
KEYWORD_OCC_CAP = 2
EXCLUDE_PENALTY = -10


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _max_contribution(c: Criterion) -> float:
    if c.kind == "skill":
        return SKILL_OCC_CAP * c.weight
    if c.kind == "role":
        return ROLE_BASE_MULT * c.weight * ROLE_TITLE_BOOST
    if c.kind == "keyword":
        return KEYWORD_OCC_CAP * c.weight
    return 0  # exclude only contributes negatively


def _theoretical_max(criteria: list[Criterion]) -> float:
    return float(sum(_max_contribution(c) for c in criteria))


def _contribution(c: Criterion, occurrences: int, in_title: bool) -> float:
    if c.kind == "exclude":
        return float(EXCLUDE_PENALTY * c.weight) if occurrences > 0 else 0.0
    if occurrences == 0:
        return 0.0
    if c.kind == "skill":
        return float(min(occurrences, SKILL_OCC_CAP) * c.weight)
    if c.kind == "role":
        base = ROLE_BASE_MULT * c.weight
        return float(base * ROLE_TITLE_BOOST if in_title else base)
    if c.kind == "keyword":
        return float(min(occurrences, KEYWORD_OCC_CAP) * c.weight)
    return 0.0


def _load_criteria(session: Session, profile_id: int) -> list[Criterion]:
    return (
        session.execute(
            select(Criterion).where(Criterion.profile_id == profile_id)
        )
        .scalars()
        .all()
    )


def score_item_raw(
    item: Item,
    profile: Profile,
    session: Session,
    criteria: list[Criterion] | None = None,
) -> tuple[float, list[dict]]:
    """Compute raw score and matched-terms list for one item. No persistence.

    Floored at zero. Used both by ``score_item`` (single-item, theoretical-
    max normalization) and by ``batch.score_all_items`` (two-pass, dataset-
    relative normalization). Pass ``criteria`` to avoid a redundant query
    when scoring many items against the same profile.
    """
    title_clean = normalize_unicode(clean_html(item.title or ""))
    body_clean = normalize_unicode(clean_html(item.body or ""))

    if criteria is None:
        criteria = _load_criteria(session, profile.id)

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

    return max(0.0, raw_score), matched


def upsert_score(
    item_id: int,
    profile_id: int,
    normalized: float,
    raw: float,
    matched: list[dict],
    session: Session,
) -> Score:
    """Insert or update a Score row keyed by (item_id, profile_id)."""
    existing = session.execute(
        select(Score).where(
            Score.item_id == item_id,
            Score.profile_id == profile_id,
        )
    ).scalar_one_or_none()

    now = _now_utc_naive()
    if existing is None:
        row = Score(
            item_id=item_id,
            profile_id=profile_id,
            score=normalized,
            raw_score=raw,
            matched_terms_json=matched,
            computed_at=now,
        )
        session.add(row)
        session.flush()
        return row

    existing.score = normalized
    existing.raw_score = raw
    existing.matched_terms_json = matched
    existing.computed_at = now
    session.flush()
    return existing


def score_item(item: Item, profile: Profile, session: Session) -> Score:
    """Score one item and persist. The ``score`` field is theoretical-max-
    normalized — for dataset-relative normalization across many items,
    use ``batch.score_all_items`` instead."""
    criteria = _load_criteria(session, profile.id)
    raw, matched = score_item_raw(item, profile, session, criteria=criteria)

    max_possible = _theoretical_max(criteria)
    if max_possible > 0:
        normalized = min(100.0, max(0.0, (raw / max_possible) * 100))
    else:
        normalized = 0.0

    return upsert_score(item.id, profile.id, normalized, raw, matched, session)
