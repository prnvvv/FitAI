"""Tests for fitness calculation tools."""
from __future__ import annotations

import pytest

from app.tools.calculations import (
    ToolInputError,
    calculate_bmi,
    calculate_bmr,
    calculate_calorie_target,
    calculate_macros,
    calculate_tdee,
)


def test_calculate_bmi_normal() -> None:
    result = calculate_bmi(70, 175)
    assert result["bmi"] == pytest.approx(22.9, 0.1)
    assert result["category"] == "normal"


def test_calculate_bmi_invalid_weight() -> None:
    with pytest.raises(ToolInputError):
        calculate_bmi(500, 175)


def test_calculate_bmr_male() -> None:
    result = calculate_bmr(70, 175, 30, "male")
    assert result["bmr_kcal"] > 0


def test_calculate_bmr_invalid_sex() -> None:
    with pytest.raises(ToolInputError):
        calculate_bmr(70, 175, 30, "other")  # type: ignore[arg-type]


def test_calculate_tdee() -> None:
    result = calculate_tdee(70, 175, 30, "male", "moderate")
    assert result["tdee_kcal"] > result["bmr_kcal"]
    assert result["activity_factor"] == 1.55


def test_calculate_calorie_target_lose() -> None:
    result = calculate_calorie_target(70, 175, 30, "male", "moderate", "lose")
    assert result["target_kcal"] < result["tdee_kcal"]


def test_calculate_calorie_target_maintain_rejects_rate() -> None:
    with pytest.raises(ToolInputError):
        calculate_calorie_target(70, 175, 30, "male", "moderate", "maintain", 0.5)


def test_calculate_calorie_target_floor() -> None:
    result = calculate_calorie_target(50, 160, 25, "female", "sedentary", "lose", 0.5)
    assert result["target_kcal"] >= 1200
    assert result["clamped_to_minimum"] is True


def test_calculate_macros() -> None:
    result = calculate_macros(2000, 70, "maintain")
    assert result["protein_g"] > 0
    assert result["fat_g"] > 0
    assert result["carbs_g"] > 0


def test_calculate_macros_invalid_goal() -> None:
    with pytest.raises(ToolInputError):
        calculate_macros(2000, 70, "cut")  # type: ignore[arg-type]
