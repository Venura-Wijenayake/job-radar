"""Sanitize a local job_radar.db so it's safe to commit to the repo.

Strips personal artifacts while preserving the scraped corpus:

  Cleared:
    DELETE FROM tracking
    DELETE FROM applications
    UPDATE profiles SET resume_raw_text = NULL, resume_filename = NULL

  Kept:
    sources, items, criteria, scores, keyword_extracts
    profiles row(s) with name + parsed_at + metadata_json (no PII text)

Idempotent. A second run on an already-sanitized DB reports
"nothing to clear" and exits without overwriting the existing backup.

Always copies the pre-sanitize DB to ``data/job_radar.db.local_backup``
on the first run so the personal state can be restored to any local
clone afterward. The backup is gitignored.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select, update

from db.database import get_session
from db.models import (
    Application,
    Criterion,
    Item,
    KeywordExtract,
    Profile,
    Score,
    Source,
    Tracking,
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "job_radar.db"
BACKUP_PATH = DB_PATH.with_name(DB_PATH.name + ".local_backup")


def _row_counts(session) -> dict[str, int]:
    return {
        "sources": session.execute(select(func.count(Source.id))).scalar_one(),
        "profiles": session.execute(select(func.count(Profile.id))).scalar_one(),
        "criteria": session.execute(select(func.count(Criterion.id))).scalar_one(),
        "items": session.execute(select(func.count(Item.id))).scalar_one(),
        "scores": session.execute(select(func.count(Score.id))).scalar_one(),
        "tracking": session.execute(select(func.count(Tracking.id))).scalar_one(),
        "applications": session.execute(select(func.count(Application.id))).scalar_one(),
        "keyword_extracts": session.execute(
            select(func.count(KeywordExtract.id))
        ).scalar_one(),
    }


def _has_personal_state(session) -> bool:
    if session.execute(select(func.count(Tracking.id))).scalar_one() > 0:
        return True
    if session.execute(select(func.count(Application.id))).scalar_one() > 0:
        return True
    pii_profiles = session.execute(
        select(func.count(Profile.id)).where(
            (Profile.resume_raw_text.is_not(None))
            | (Profile.resume_filename.is_not(None))
        )
    ).scalar_one()
    if pii_profiles > 0:
        return True
    return False


def main() -> None:
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}; nothing to do.")
        return

    with get_session() as session:
        counts_before = _row_counts(session)
        has_personal = _has_personal_state(session)

    print("Row counts BEFORE:")
    for table, n in counts_before.items():
        print(f"  {table:<18} {n}")

    if not has_personal:
        print()
        print("Nothing to clear — DB is already sanitized.")
        return

    if BACKUP_PATH.exists():
        print()
        print(f"Backup already exists at {BACKUP_PATH}; not overwriting.")
    else:
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print()
        print(f"Backup written to {BACKUP_PATH}")

    with get_session() as session:
        cleared_tracking = session.execute(delete(Tracking)).rowcount or 0
        cleared_apps = session.execute(delete(Application)).rowcount or 0
        pii_update = session.execute(
            update(Profile)
            .where(
                (Profile.resume_raw_text.is_not(None))
                | (Profile.resume_filename.is_not(None))
            )
            .values(resume_raw_text=None, resume_filename=None)
        )
        cleared_profile_pii = pii_update.rowcount or 0
        session.commit()

    with get_session() as session:
        counts_after = _row_counts(session)

    print()
    print("Cleared:")
    print(f"  {cleared_tracking} tracking row(s)")
    print(f"  {cleared_apps} application row(s)")
    print(
        f"  {cleared_profile_pii} profile row(s) had "
        "resume_raw_text + resume_filename set to NULL"
    )

    print()
    print("Row counts AFTER:")
    for table, n in counts_after.items():
        print(f"  {table:<18} {n}")


if __name__ == "__main__":
    main()
