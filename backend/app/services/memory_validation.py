"""Validation for structured memory values.

Current memory stores a typed value per :class:`MemoryKey`. Values are validated
before persistence so that arbitrary unvalidated JSON cannot become an accepted
fact. The exact per-key shapes are **provisional** pending agreement with
Person 2.
"""

from __future__ import annotations

import json

from app.core.errors import ValidationError
from app.models.enums import ActivityLevel, MemoryKey

_MEASUREMENT_UNITS: dict[MemoryKey, frozenset[str]] = {
    MemoryKey.WEIGHT: frozenset({"kg", "lb"}),
    MemoryKey.HEIGHT: frozenset({"cm", "in"}),
}

_STRING_KEYS = frozenset({MemoryKey.GOAL, MemoryKey.EXPERIENCE_LEVEL, MemoryKey.WORKOUT_FREQUENCY})

_LIST_KEYS = frozenset(
    {
        MemoryKey.DIETARY_PREFERENCES,
        MemoryKey.DIETARY_RESTRICTIONS,
        MemoryKey.SUPPLEMENTS,
    }
)


def validate_memory_value(key: MemoryKey, value: object) -> None:
    """Validate ``value`` for ``key`` or raise :class:`ValidationError`."""
    if value is None:
        raise ValidationError(
            "Memory value must not be null.",
            details={"key": key.value},
        )
    _ensure_json_serializable(value, key)

    if key in _MEASUREMENT_UNITS:
        _validate_measurement(key, value)
        return
    if key == MemoryKey.ACTIVITY_LEVEL:
        _validate_activity_level(value)
        return
    if key in _STRING_KEYS:
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(
                "Memory value must be a non-empty string.",
                details={"key": key.value},
            )
        return
    if key in _LIST_KEYS and not isinstance(value, list):
        raise ValidationError(
            "Memory value must be a list.",
            details={"key": key.value},
        )


def _validate_measurement(key: MemoryKey, value: object) -> None:
    allowed_units = _MEASUREMENT_UNITS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if not isinstance(value, dict):
            raise ValidationError(
                "Measurement must be a number or an object with 'value' and 'unit'.",
                details={"key": key.value},
            )
        numeric = value.get("value")
        unit = value.get("unit")
        if isinstance(numeric, bool) or not isinstance(numeric, (int, float)):
            raise ValidationError(
                "Measurement 'value' must be a number.",
                details={"key": key.value},
            )
        if unit not in allowed_units:
            raise ValidationError(
                "Measurement unit is not supported.",
                details={"key": key.value, "unit": unit, "allowed": sorted(allowed_units)},
            )
    else:
        numeric = value
    if numeric <= 0:
        raise ValidationError(
            "Measurement value must be greater than zero.",
            details={"key": key.value},
        )


def _validate_activity_level(value: object) -> None:
    allowed = {level.value for level in ActivityLevel}
    if value not in allowed:
        raise ValidationError(
            "Activity level is not recognized.",
            details={"allowed": sorted(allowed)},
        )


def _ensure_json_serializable(value: object, key: MemoryKey) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Memory value is not JSON-serializable.",
            details={"key": key.value},
        ) from exc
