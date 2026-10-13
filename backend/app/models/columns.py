"""Shared SQLAlchemy column helpers."""

from __future__ import annotations

from enum import EnumMeta

from sqlalchemy import Enum as SAEnum


def enum_type(enum_cls: EnumMeta, name: str) -> SAEnum:
    """Build a portable enum column type that stores enum *values*.

    ``native_enum=False`` renders a VARCHAR + CHECK constraint, which avoids
    PostgreSQL type-creation complexity in migrations.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )
