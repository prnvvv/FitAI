"""Startup verification that the configured database has the expected schema."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]
REQUIRED_TABLES = ("users", "documents", "conversations", "messages")


class DatabaseSchemaError(RuntimeError):
    """The configured database is unusable or not migrated to the latest revision."""


def alembic_head_revision() -> str | None:
    """Return the migration head, independent of the process working directory."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def is_ephemeral_sqlite(database_url: str) -> bool:
    """True for SQLite URLs that name no file, i.e. a private in-memory database."""
    url = make_url(database_url)
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


def verify_database_schema(engine: Engine, head_revision: str | None) -> None:
    """Raise ``DatabaseSchemaError`` unless the database is migrated to ``head_revision``."""
    if is_ephemeral_sqlite(str(engine.url)):
        raise DatabaseSchemaError(
            "DATABASE_URL points at an in-memory SQLite database that is always empty "
            "and cannot hold migrations. Set DATABASE_URL to the PostgreSQL (Supabase) "
            "database, e.g. postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DB, "
            "then run: alembic upgrade head"
        )

    with engine.connect() as conn:
        try:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception as exc:  # noqa: BLE001 - any failure means no usable version table
            raise DatabaseSchemaError(
                "Database has no alembic_version table; migrations have not been applied. "
                "Run: alembic upgrade head"
            ) from exc
        if current != head_revision:
            raise DatabaseSchemaError(
                f"Database migration mismatch: current={current}, head={head_revision}. "
                "Run: alembic upgrade head"
            )
        existing = set(inspect(conn).get_table_names())

    missing = [t for t in REQUIRED_TABLES if t not in existing]
    if missing:
        raise DatabaseSchemaError(f"Database is missing required tables: {', '.join(missing)}")


def find_foreign_key_violations(engine: Engine) -> list[dict[str, object]]:
    """Report rows whose foreign key points at a missing parent (SQLite only).

    Read-only: ``PRAGMA foreign_key_check`` never modifies data. Databases
    written before FK enforcement was enabled may hold such orphans; they are
    reported, never deleted. Returns an empty list for other dialects, where the
    database enforces constraints itself.
    """
    if engine.dialect.name != "sqlite":
        return []
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    return [{"table": r[0], "rowid": r[1], "parent_table": r[2], "fk_index": r[3]} for r in rows]
