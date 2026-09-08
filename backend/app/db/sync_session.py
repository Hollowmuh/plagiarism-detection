"""Synchronous database session for Celery tasks.

Celery tasks run outside the async FastAPI event loop,
so they need a traditional sync SQLAlchemy session.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_session_factory = None


def get_sync_session() -> Session:
    """Get a sync database session (creates engine on first call)."""
    global _engine, _session_factory

    if _session_factory is None:
        url = os.getenv(
            "DATABASE_URL_SYNC",
            "postgresql://plagiarism:plagiarism@localhost:5432/plagiarism",
        )
        _engine = create_engine(url, pool_pre_ping=True, pool_size=5)
        _session_factory = sessionmaker(bind=_engine)

    return _session_factory()
