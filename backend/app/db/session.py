"""SQLAlchemy engine, session factory, and request-scoped dependency."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def enable_sqlite_foreign_keys(engine: Engine) -> Engine:
    """Turn on FK enforcement for every SQLite connection the engine opens.

    SQLite ignores foreign keys unless ``PRAGMA foreign_keys=ON`` is issued on
    each connection, so the ``ON DELETE CASCADE`` rules in the schema would
    otherwise be silently skipped. The pragma is per-connection, hence the
    ``connect`` hook rather than a one-off statement. Alembic builds its own
    engine and is deliberately left alone: batch table rebuilds on SQLite must
    run with enforcement off.
    """

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def build_engine(database_url: str) -> Engine:
    """Create an engine with connection settings appropriate for the dialect.

    SQLite is supported so that tests can run without PostgreSQL; the PostgreSQL
    branch adds pre-ping and pool sizing suitable for a remote Supabase instance.
    """
    if database_url.startswith("sqlite"):
        return enable_sqlite_foreign_keys(
            create_engine(
                database_url,
                future=True,
                connect_args={"check_same_thread": False},
            )
        )
    return create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
        echo=settings.db_echo,
    )


engine: Engine = build_engine(settings.database_url)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy session and always close it afterwards.

    The session is not committed automatically; services are responsible for
    committing or rolling back their own transaction boundaries.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
