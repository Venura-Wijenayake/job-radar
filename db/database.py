from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

load_dotenv()


def _db_url() -> str:
    db_path = os.getenv("DATABASE_PATH", "data/job_radar.db")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


@lru_cache(maxsize=8)
def _engine_for(url: str) -> Engine:
    return create_engine(url, future=True)


@lru_cache(maxsize=8)
def _sessionmaker_for(url: str) -> sessionmaker:
    return sessionmaker(bind=_engine_for(url), expire_on_commit=False)


def get_engine() -> Engine:
    return _engine_for(_db_url())


def get_session() -> Session:
    return _sessionmaker_for(_db_url())()


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def reset_caches() -> None:
    _engine_for.cache_clear()
    _sessionmaker_for.cache_clear()
