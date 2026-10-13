"""Dated body measurements.

Measurements are append-only: recording a new value never overwrites a prior
entry, so the user's history is preserved.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.columns import enum_type
from app.models.enums import MeasurementType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Measurement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A recorded measurement value at a point in time."""

    __tablename__ = "measurements"
    __table_args__ = (
        Index("ix_measurements_user_type_measured", "user_id", "type", "measured_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[MeasurementType] = mapped_column(
        enum_type(MeasurementType, "measurement_type"),
        nullable=False,
    )
    value: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    user: Mapped[User] = relationship(back_populates="measurements")
