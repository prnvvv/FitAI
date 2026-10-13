"""Tests for deterministic safety guardrails."""
from __future__ import annotations

import pytest

from app.safety import SafetyResult, run_safety_rules


@pytest.mark.parametrize("message,category", [
    ("I want to kill myself", "self_harm"),
    ("I have chest pain and can't breathe", "medical_emergency"),
    ("I want to starve myself and eat under 800 calories", "extreme_restriction"),
    ("What dosage of trenbolone should I inject in a 500mg cycle?", "drug_dosing"),
])
def test_run_safety_rules_blocks(message: str, category: str) -> None:
    result = run_safety_rules(message)
    assert result.blocked is True
    assert result.category == category
    assert result.response is not None
    assert len(result.response) > 0


def test_run_safety_rules_allows_safe_message() -> None:
    result = run_safety_rules("What is a good high-protein breakfast?")
    assert result.blocked is False
    assert result.category is None
    assert result.response is None


def test_safety_result_defaults() -> None:
    result = SafetyResult()
    assert result.blocked is False
    assert result.category is None
    assert result.response is None
