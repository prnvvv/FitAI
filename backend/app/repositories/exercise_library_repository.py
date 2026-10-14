"""Exercise library persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.exercise_library import ExerciseLibrary


class ExerciseLibraryRepository:
    """Persistence for canonical and custom exercises."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        search: str | None = None,
        muscle_group: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[ExerciseLibrary], int]:
        """Return canonical exercises plus the user's custom exercises."""
        filters = [or_(ExerciseLibrary.user_id.is_(None), ExerciseLibrary.user_id == user_id)]
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    ExerciseLibrary.name.ilike(term),
                    ExerciseLibrary.primary_muscle_group.ilike(term),
                    ExerciseLibrary.equipment.ilike(term),
                )
            )
        if muscle_group:
            filters.append(ExerciseLibrary.primary_muscle_group.ilike(muscle_group))

        total = self._db.scalar(select(func.count()).select_from(ExerciseLibrary).where(*filters))
        statement = (
            select(ExerciseLibrary)
            .where(*filters)
            .order_by(ExerciseLibrary.name)
            .limit(limit)
            .offset(offset)
        )
        return list(self._db.scalars(statement)), int(total or 0)

    def get(self, exercise_id: uuid.UUID, user_id: uuid.UUID) -> ExerciseLibrary | None:
        """Return the exercise if visible to the user."""
        return self._db.scalar(
            select(ExerciseLibrary).where(
                ExerciseLibrary.id == exercise_id,
                or_(ExerciseLibrary.user_id.is_(None), ExerciseLibrary.user_id == user_id),
            )
        )

    def get_by_slug(self, slug: str, user_id: uuid.UUID | None) -> ExerciseLibrary | None:
        """Return a canonical or user-owned exercise by slug."""
        filters = [ExerciseLibrary.slug == slug]
        if user_id is None:
            filters.append(ExerciseLibrary.user_id.is_(None))
        else:
            filters.append(
                or_(ExerciseLibrary.user_id.is_(None), ExerciseLibrary.user_id == user_id)
            )
        return self._db.scalar(select(ExerciseLibrary).where(*filters))

    def create_custom(
        self,
        user_id: uuid.UUID,
        slug: str,
        name: str,
        *,
        primary_muscle_group: str | None = None,
        equipment: str | None = None,
        movement_type: str | None = None,
        unit_mode: str = "reps_weight",
    ) -> ExerciseLibrary:
        """Create a private custom exercise for the user."""
        exercise = ExerciseLibrary(
            slug=slug,
            name=name,
            primary_muscle_group=primary_muscle_group,
            equipment=equipment,
            movement_type=movement_type,
            unit_mode=unit_mode,
            is_custom=True,
            user_id=user_id,
        )
        self._db.add(exercise)
        return exercise

    def list_muscle_groups(self, user_id: uuid.UUID) -> list[str]:
        """Return distinct muscle groups visible to the user."""
        statement = (
            select(ExerciseLibrary.primary_muscle_group)
            .where(
                or_(ExerciseLibrary.user_id.is_(None), ExerciseLibrary.user_id == user_id),
                ExerciseLibrary.primary_muscle_group.is_not(None),
            )
            .distinct()
            .order_by(ExerciseLibrary.primary_muscle_group)
        )
        return [str(g) for g in self._db.scalars(statement) if g]

    def list_recent(
        self, user_id: uuid.UUID, exercise_names: Sequence[str]
    ) -> list[ExerciseLibrary]:
        """Return library entries matching the given exercise names, newest first."""
        if not exercise_names:
            return []
        statement = (
            select(ExerciseLibrary)
            .where(
                or_(ExerciseLibrary.user_id.is_(None), ExerciseLibrary.user_id == user_id),
                ExerciseLibrary.name.in_(exercise_names),
            )
            .order_by(ExerciseLibrary.updated_at.desc())
            .limit(20)
        )
        return list(self._db.scalars(statement))
