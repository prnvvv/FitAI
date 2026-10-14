"""The bundled exercise seed must be idempotent and complete."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.seed import seed_exercises
from app.models.exercise_library import ExerciseLibrary
from app.services.exercise_library_service import ExerciseLibraryService

VALID_MOVEMENT_TYPES = {"push", "pull", "legs", "core", "cardio", "mobility"}
VALID_UNIT_MODES = {"reps_weight", "reps_only", "time", "distance"}


def _bundled() -> list[dict[str, str]]:
    from app.db.seed import _exercise_data_path

    raw = json.loads(_exercise_data_path().read_text(encoding="utf-8"))
    return raw["exercises"]


def test_seed_file_is_versioned_and_populated() -> None:
    from app.db.seed import _exercise_data_path

    raw = json.loads(_exercise_data_path().read_text(encoding="utf-8"))
    assert raw["version"] >= 1
    assert len(raw["exercises"]) >= 100


def test_seed_inserts_then_updates_without_duplicating(db_session: Session) -> None:
    assert seed_exercises(db_session) == len(_bundled())
    total_after_first = db_session.scalar(select(func.count()).select_from(ExerciseLibrary))
    assert total_after_first == len(_bundled())

    # Running it again must not duplicate rows.
    assert seed_exercises(db_session) == len(_bundled())
    total_after_second = db_session.scalar(select(func.count()).select_from(ExerciseLibrary))
    assert total_after_second == total_after_first


def test_seeded_exercises_are_canonically_shaped(db_session: Session) -> None:
    seed_exercises(db_session)
    items = db_session.scalars(select(ExerciseLibrary)).all()

    slugs = {item.slug for item in items}
    assert len(slugs) == len(items)  # unique by slug
    for item in items:
        assert item.name
        assert item.user_id is None
        assert item.is_custom is False
        assert item.unit_mode in VALID_UNIT_MODES
        assert item.movement_type in VALID_MOVEMENT_TYPES


def test_named_examples_are_present(db_session: Session) -> None:
    seed_exercises(db_session)
    names = {item.name for item in db_session.scalars(select(ExerciseLibrary))}
    for expected in [
        "Barbell Back Squat",
        "Front Squat",
        "Goblet Squat",
        "Romanian Deadlift",
        "Conventional Deadlift",
        "Leg Press",
        "Walking Lunge",
        "Bulgarian Split Squat",
        "Leg Curl",
        "Leg Extension",
        "Calf Raise",
        "Hip Thrust",
        "Bench Press",
        "Incline Dumbbell Press",
        "Overhead Press",
        "Dumbbell Shoulder Press",
        "Lateral Raise",
        "Push-up",
        "Dips",
        "Triceps Pushdown",
        "Skull Crusher",
        "Pull-up",
        "Chin-up",
        "Lat Pulldown",
        "Barbell Row",
        "Seated Cable Row",
        "Dumbbell Row",
        "Face Pull",
        "Bicep Curl",
        "Hammer Curl",
        "Plank",
        "Crunch",
        "Hanging Leg Raise",
        "Russian Twist",
        "Running",
        "Cycling",
        "Rowing Machine",
        "Jump Rope",
        "Walking",
        "Stretching",
        "Yoga Flow",
    ]:
        assert expected in names, expected


def test_custom_exercises_are_private_to_their_owner(db_session: Session) -> None:
    owner, other = uuid.uuid4(), uuid.uuid4()
    service = ExerciseLibraryService(db_session)

    custom = service.create_custom(owner, "Cable Y raise", unit_mode="reps_weight")
    assert custom.is_custom is True

    owner_names = {
        e.name for e in service.list_exercises(owner, search="y raise", limit=50, offset=0)[0]
    }
    other_names = {
        e.name for e in service.list_exercises(other, search="y raise", limit=50, offset=0)[0]
    }
    assert "Cable Y raise" in owner_names
    assert "Cable Y raise" not in other_names
