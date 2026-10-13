"""Profile request and response schemas."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.enums import ActivityLevel

MIN_DATE_OF_BIRTH = dt.date(1900, 1, 1)


class _ProfileFields(BaseModel):
    """Validation shared by PUT and PATCH profile payloads."""

    date_of_birth: dt.date | None = None
    height_cm: Decimal | None = Field(default=None, gt=0, le=300)
    weight_kg: Decimal | None = Field(default=None, gt=0, le=700)
    goal: str | None = Field(default=None, max_length=200)
    activity_level: ActivityLevel | None = None
    dietary_preferences: list[str] | None = None
    dietary_restrictions: list[str] | None = None
    supplements: list[dict[str, object]] | None = None
    preferences: dict[str, object] | None = None
    location_label: str | None = Field(default=None, max_length=255)
    location_lat: Decimal | None = None
    location_lon: Decimal | None = None
    location_timezone: str | None = Field(default=None, max_length=64)

    @field_validator("date_of_birth")
    @classmethod
    def _validate_date_of_birth(cls, value: dt.date | None) -> dt.date | None:
        if value is None:
            return None
        if value > dt.date.today():
            raise ValueError("Date of birth cannot be in the future.")
        if value < MIN_DATE_OF_BIRTH:
            raise ValueError("Date of birth is implausibly old.")
        return value


class ProfileUpdate(_ProfileFields):
    """Full profile replacement (PUT). Omitted fields are cleared."""


class ProfilePatch(_ProfileFields):
    """Partial profile update (PATCH). Only supplied fields change."""


class ProfileOut(_ProfileFields):
    """Profile representation returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    created_at: dt.datetime
    updated_at: dt.datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def age(self) -> int | None:
        """Derive age from date of birth; age is never stored."""
        if self.date_of_birth is None:
            return None
        today = dt.date.today()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )
