"""Integration: the agent's fitness-context adapter returns REAL records.

Uses the real WorkoutService/ProgressService against in-memory SQLite so we
prove that persisted workout sessions and progress measurements are shaped into
the context the LLM is grounded in (no mock data).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.enums import MeasurementType, WeightUnit
from app.repositories.user_repository import UserRepository
from app.services.chat_service import _FitnessReaderAdapter
from app.services.workout_service import WorkoutService


def test_fitness_context_reflects_persisted_records(db_session: Session) -> None:
    user_id = uuid4()
    UserRepository(db_session).get_or_create(user_id, "fitness@example.com")
    service = WorkoutService(db_session)
    now = datetime.now(timezone.utc)

    service.create_measurement(
        user_id, MeasurementType.WEIGHT, Decimal("80"), "kg", now - timedelta(days=30)
    )
    service.create_measurement(
        user_id, MeasurementType.WEIGHT, Decimal("78"), "kg", now - timedelta(days=1)
    )
    service.create_session(
        user_id,
        now - timedelta(days=5),
        name="Push day",
        duration_minutes=45,
        sets=[
            {
                "exercise_name": "bench press",
                "reps": 5,
                "weight": Decimal("80"),
                "weight_unit": WeightUnit.KG,
            },
            {
                "exercise_name": "overhead press",
                "reps": 8,
                "weight": Decimal("40"),
                "weight_unit": WeightUnit.KG,
            },
        ],
    )

    adapter = _FitnessReaderAdapter(db_session, user_id)
    context = adapter.get_fitness_context(str(user_id))

    assert "error" not in context
    assert context["window_days"] == 120

    totals = context["totals"]
    assert totals["sessions_completed"] == 1
    # 80kg x 5 + 40kg x 8 = 720 kg of volume from the single session.
    assert totals["total_volume_kg"] == 720.0

    weight = context["weight"]
    assert weight["points"] == 2
    assert weight["first"]["value"] == 80.0
    assert weight["latest"]["value"] == 78.0
    assert weight["change"] == -2.0

    assert len(context["recent_sessions"]) == 1
    session = context["recent_sessions"][0]
    assert session["name"] == "Push day"
    assert session["sets"] == 2
    assert "bench press" in session["exercises"]
    assert session["top"]["exercise"] == "bench press"
    assert session["top"]["weight"] == 80.0

    assert any(
        pr["exercise"] == "bench press" and pr["weight"] == 80.0
        for pr in context["personal_records"]
    )
