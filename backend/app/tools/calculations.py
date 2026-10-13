"""Validated nutrition calculations, exposed as LangGraph/LangChain tools.

Formulas / sources (estimates, not medical advice):
- BMI = kg / m^2; categories per WHO adult cut-offs.
- BMR: Mifflin-St Jeor (1990): 10*kg + 6.25*cm - 5*age + 5 (male) / - 161 (female).
- TDEE = BMR * activity factor (1.2, 1.375, 1.55, 1.725, 1.9).
- Energy balance: ~7700 kcal per kg of body mass (approximation).
- Protein 1.6-2.2 g/kg is the commonly cited range for resistance training; fat default 25% of kcal.
"""
import math
from typing import Any, Literal

from langchain_core.tools import StructuredTool, ToolException

Sex = Literal["male", "female"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
Goal = Literal["lose", "maintain", "gain"]

ACTIVITY_FACTORS = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
KCAL_PER_KG = 7700
MIN_CALORIES = {"male": 1500, "female": 1200}
DEFAULT_PROTEIN_G_PER_KG = {"lose": 2.0, "maintain": 1.6, "gain": 1.8}
DEFAULT_RATE_KG_PER_WEEK = {"lose": 0.5, "gain": 0.25}


class ToolInputError(ToolException, ValueError):
    """Invalid tool input; the message is returned to the model/user."""


def _num(name: str, value: Any, lo: float, hi: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ToolInputError(f"{name} must be a number")
    x = float(value)
    if not math.isfinite(x) or not lo <= x <= hi:
        raise ToolInputError(f"{name} must be between {lo:g} and {hi:g}")
    return x


def _person(weight_kg: Any, height_cm: Any, age_years: Any, sex: Any) -> tuple[float, float, float, str]:
    if sex not in MIN_CALORIES:
        raise ToolInputError("sex must be 'male' or 'female'")
    return (_num("weight_kg", weight_kg, 20, 400), _num("height_cm", height_cm, 100, 250),
            _num("age_years", age_years, 18, 100), sex)


def _bmr(w: float, h: float, a: float, sex: str) -> float:
    return 10 * w + 6.25 * h - 5 * a + (5 if sex == "male" else -161)


def _factor(activity_level: Any) -> float:
    if activity_level not in ACTIVITY_FACTORS:
        raise ToolInputError(f"activity_level must be one of {sorted(ACTIVITY_FACTORS)}")
    return ACTIVITY_FACTORS[activity_level]


def calculate_bmi(weight_kg: float, height_cm: float) -> dict[str, Any]:
    """Body Mass Index (adults) from weight in kg and height in cm, with WHO category."""
    w, h = _num("weight_kg", weight_kg, 20, 400), _num("height_cm", height_cm, 100, 250)
    bmi = w / (h / 100) ** 2
    cat = "underweight" if bmi < 18.5 else "normal" if bmi < 25 else "overweight" if bmi < 30 else "obese"
    return {"bmi": round(bmi, 1), "category": cat, "formula": "kg / m^2",
            "note": "Screening metric for adults; does not distinguish muscle from fat."}


def calculate_bmr(weight_kg: float, height_cm: float, age_years: int, sex: Sex) -> dict[str, Any]:
    """Basal metabolic rate (kcal/day) using Mifflin-St Jeor. Adults 18-100."""
    w, h, a, s = _person(weight_kg, height_cm, age_years, sex)
    return {"bmr_kcal": round(_bmr(w, h, a, s)), "formula": "Mifflin-St Jeor"}


def calculate_tdee(weight_kg: float, height_cm: float, age_years: int, sex: Sex,
                   activity_level: ActivityLevel) -> dict[str, Any]:
    """Total daily energy expenditure (kcal/day) = BMR x activity factor."""
    w, h, a, s = _person(weight_kg, height_cm, age_years, sex)
    f = _factor(activity_level)
    bmr = _bmr(w, h, a, s)
    return {"bmr_kcal": round(bmr), "activity_factor": f, "tdee_kcal": round(bmr * f),
            "formula": "Mifflin-St Jeor x activity factor"}


def calculate_calorie_target(weight_kg: float, height_cm: float, age_years: int, sex: Sex,
                             activity_level: ActivityLevel, goal: Goal,
                             rate_kg_per_week: float | None = None) -> dict[str, Any]:
    """Daily calorie target for lose/maintain/gain. Rate limits: lose 0.1-1.0 kg/wk (max 1% body
    weight), gain 0.05-0.5 kg/wk. Never goes below 1500 (male) / 1200 (female) kcal."""
    w, h, a, s = _person(weight_kg, height_cm, age_years, sex)
    tdee = _bmr(w, h, a, s) * _factor(activity_level)
    if goal == "maintain":
        if rate_kg_per_week not in (None, 0):
            raise ToolInputError("rate_kg_per_week must be empty for 'maintain'")
        rate = 0.0
    elif goal == "lose":
        rate = (min(DEFAULT_RATE_KG_PER_WEEK["lose"], 0.01 * w) if rate_kg_per_week is None
                else _num("rate_kg_per_week", rate_kg_per_week, 0.1, 1.0))
        if rate > 0.01 * w:
            raise ToolInputError("loss rate exceeds 1% of body weight per week")
    elif goal == "gain":
        rate = (DEFAULT_RATE_KG_PER_WEEK["gain"] if rate_kg_per_week is None
                else _num("rate_kg_per_week", rate_kg_per_week, 0.05, 0.5))
    else:
        raise ToolInputError("goal must be 'lose', 'maintain' or 'gain'")

    adjustment = rate * KCAL_PER_KG / 7
    raw = tdee - adjustment if goal == "lose" else tdee + adjustment
    floor = MIN_CALORIES[s]
    return {"tdee_kcal": round(tdee), "daily_adjustment_kcal": round(adjustment) * (-1 if goal == "lose" else 1),
            "target_kcal": round(max(raw, floor)), "rate_kg_per_week": round(rate, 2),
            "clamped_to_minimum": raw < floor, "assumption": f"{KCAL_PER_KG} kcal per kg"}


def calculate_macros(calorie_target_kcal: float, weight_kg: float, goal: Goal,
                     protein_g_per_kg: float | None = None, fat_percent: float = 25) -> dict[str, Any]:
    """Macro split in grams: protein by body weight (default 2.0/1.6/1.8 g/kg for lose/maintain/gain),
    fat as % of calories (15-40, floor 0.6 g/kg), carbohydrate = remainder."""
    cal = _num("calorie_target_kcal", calorie_target_kcal, 800, 8000)
    w = _num("weight_kg", weight_kg, 20, 400)
    if goal not in DEFAULT_PROTEIN_G_PER_KG:
        raise ToolInputError("goal must be 'lose', 'maintain' or 'gain'")
    p_per_kg = (DEFAULT_PROTEIN_G_PER_KG[goal] if protein_g_per_kg is None
                else _num("protein_g_per_kg", protein_g_per_kg, 1.2, 3.0))
    fat_pct = _num("fat_percent", fat_percent, 15, 40)

    protein_g = p_per_kg * w
    fat_g = max(cal * fat_pct / 100 / 9, 0.6 * w)
    carbs_g = (cal - protein_g * 4 - fat_g * 9) / 4
    if carbs_g < 0:
        raise ToolInputError("calorie target is too low for the protein and fat minimums")
    pct = lambda kcal: round(100 * kcal / cal, 1)  # noqa: E731
    return {"protein_g": round(protein_g), "fat_g": round(fat_g), "carbs_g": round(carbs_g),
            "percent_of_calories": {"protein": pct(protein_g * 4), "fat": pct(fat_g * 9),
                                    "carbs": pct(carbs_g * 4)},
            "kcal_per_gram": {"protein": 4, "carbs": 4, "fat": 9}}


def _as_tool(fn) -> StructuredTool:
    return StructuredTool.from_function(fn, name=fn.__name__, description=(fn.__doc__ or "").strip(),
                                        handle_tool_error=True)


CALCULATION_TOOLS = [_as_tool(f) for f in (calculate_bmi, calculate_bmr, calculate_tdee,
                                           calculate_calorie_target, calculate_macros)]
