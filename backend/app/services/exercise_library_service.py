"""Exercise library business logic."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.exercise_library import ExerciseLibrary
from app.repositories.exercise_library_repository import ExerciseLibraryRepository


def _make_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return base or "exercise"


class ExerciseLibraryService:
    """Catalogue of canonical and custom exercises."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = ExerciseLibraryRepository(db)

    def list_exercises(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None = None,
        muscle_group: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[ExerciseLibrary], int]:
        return self._repo.list_for_user(
            user_id, search=search, muscle_group=muscle_group, limit=limit, offset=offset
        )

    def create_custom(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        primary_muscle_group: str | None = None,
        equipment: str | None = None,
        movement_type: str | None = None,
        unit_mode: str = "reps_weight",
    ) -> ExerciseLibrary:
        slug = _make_slug(name)
        existing = self._repo.get_by_slug(slug, user_id)
        if existing is not None:
            raise ConflictError("An exercise with this name already exists.")
        exercise = self._repo.create_custom(
            user_id,
            slug,
            name,
            primary_muscle_group=primary_muscle_group,
            equipment=equipment,
            movement_type=movement_type,
            unit_mode=unit_mode,
        )
        self._commit()
        self._db.refresh(exercise)
        return exercise

    def get(self, exercise_id: uuid.UUID, user_id: uuid.UUID) -> ExerciseLibrary:
        exercise = self._repo.get(exercise_id, user_id)
        if exercise is None:
            raise NotFoundError("Exercise not found.")
        return exercise

    def list_muscle_groups(self, user_id: uuid.UUID) -> list[str]:
        return self._repo.list_muscle_groups(user_id)

    def list_recent(self, user_id: uuid.UUID, exercise_names: list[str]) -> list[ExerciseLibrary]:
        return self._repo.list_recent(user_id, exercise_names)

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError as exc:
            self._db.rollback()
            raise AppError("The exercise could not be saved.") from exc
