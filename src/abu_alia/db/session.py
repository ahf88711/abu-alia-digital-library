from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from abu_alia.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def get_engine(settings: Optional[Settings] = None) -> Engine:
    global _engine
    settings = settings or get_settings()
    if _engine is None:
        connect_args = {}
        if settings.is_sqlite:
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            settings.database_url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if settings.is_sqlite:
            _configure_sqlite(_engine)
    return _engine


def get_session_factory(settings: Optional[Settings] = None) -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(settings),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _session_factory


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def init_db(settings: Optional[Settings] = None) -> None:
    # Imported lazily so models register on Base.metadata
    from abu_alia.db import models  # noqa: F401

    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    settings = settings or get_settings()
    if settings.is_sqlite:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5("
                    "work_id UNINDEXED, title, authors, categories, publisher, "
                    "identifiers, body, tokenize='unicode61')"
                )
            )


@contextmanager
def session_scope(settings: Optional[Settings] = None) -> Iterator[Session]:
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
