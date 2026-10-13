"""User fitness profile."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import ActivityLevel
from app.models.mixins import JSONType, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Profile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Structured fitness profile for a user.

    Age is intentionally *not* stored; it is derived from ``date_of_birth``.
    ``weight_kg`` is the profile's stated current weight; dated weight history
    lives in the measurements table. BMI is derived, never persisted.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    goal: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activity_level: Mapped[ActivityLevel | None] = mapped_column(
        enum_type(ActivityLevel, "activity_level"),
        nullable=True,
    )
    dietary_preferences: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    dietary_restrictions: Mapped[list[str] | None] = mapped_column(JSONType, nullable=True)
    supplements: Mapped[list[dict[str, object]] | None] = mapped_column(JSONType, nullable=True)
    preferences: Mapped[dict[str, object] | None] = mapped_column(JSONType, nullable=True)

    # Optional real-world location, stored with reduced precision and never logged.
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_lat: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    location_lon: Mapped[Decimal | None] = mapped_column(Numeric(8, 5), nullable=True)
    location_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="profile")
