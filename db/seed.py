from __future__ import annotations

from sqlalchemy import select

from .database import get_session
from .models import Source

DEFAULT_SOURCES = [
    {
        "name": "RemoteOK",
        "type": "api",
        "url": "https://remoteok.com/api",
        "enabled": True,
    },
]


def seed_sources() -> int:
    """Insert default sources if missing. Returns count of newly inserted rows."""
    inserted = 0
    with get_session() as session:
        for spec in DEFAULT_SOURCES:
            existing = session.execute(
                select(Source).where(Source.name == spec["name"])
            ).scalar_one_or_none()
            if existing is None:
                session.add(Source(**spec))
                inserted += 1
        if inserted:
            session.commit()
    return inserted
