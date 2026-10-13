"""Unit tests for structured memory value validation."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.models.enums import MemoryKey
from app.services.memory_validation import validate_memory_value


def test_weight_accepts_object_with_unit() -> None:
    validate_memory_value(MemoryKey.WEIGHT, {"value": 72.5, "unit": "kg"})


def test_weight_accepts_bare_number() -> None:
    validate_memory_value(MemoryKey.WEIGHT, 72.5)


def test_weight_rejects_unknown_unit() -> None:
    with pytest.raises(ValidationError):
        validate_memory_value(MemoryKey.WEIGHT, {"value": 72.5, "unit": "stone"})


def test_weight_rejects_non_positive() -> None:
    with pytest.raises(ValidationError):
        validate_memory_value(MemoryKey.WEIGHT, 0)


def test_activity_level_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        validate_memory_value(MemoryKey.ACTIVITY_LEVEL, "superhuman")


def test_list_key_requires_list() -> None:
    validate_memory_value(MemoryKey.DIETARY_PREFERENCES, ["high protein"])
    with pytest.raises(ValidationError):
        validate_memory_value(MemoryKey.DIETARY_PREFERENCES, "high protein")


def test_string_key_requires_non_empty() -> None:
    validate_memory_value(MemoryKey.GOAL, "build muscle")
    with pytest.raises(ValidationError):
        validate_memory_value(MemoryKey.GOAL, "   ")


def test_none_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_memory_value(MemoryKey.GOAL, None)
