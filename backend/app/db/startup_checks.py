"""Start-up database verification shared by every service."""

from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)


def check_migrations_at_startup() -> None:
    """Fail loudly if the database is unusable or behind the latest migration.

    This prevents cryptic 500s from missing tables/columns and tells operators
    exactly what to do. It checks the same engine the application uses.
    """
    from app.db.schema_check import (
        alembic_head_revision,
        find_foreign_key_violations,
        verify_database_schema,
    )
    from app.db.session import engine

    verify_database_schema(engine, alembic_head_revision())
    # Report (never delete) rows orphaned before FK enforcement was enabled.
    try:
        violations = find_foreign_key_violations(engine)
    except Exception:  # diagnostic only; must not block startup
        logger.warning("foreign_key_check_failed", exc_info=True)
    else:
        if violations:
            logger.warning(
                "foreign_key_violations_found",
                count=len(violations),
                tables=sorted({str(v["table"]) for v in violations}),
                hint="Back up the database, then run backend/scripts/check_orphans.py to inspect.",
            )
