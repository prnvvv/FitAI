"""Idempotent database seeding.

Run from the project root with:

    python -m app.db.seed
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.exercise_library import ExerciseLibrary

log = logging.getLogger(__name__)


def _exercise_data_path() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve().parent
    return here.parent / "data" / "exercises.json"


def seed_exercises(db: Session) -> int:
    """Upsert canonical exercises from the bundled JSON file.

    Existing seeded exercises (``user_id IS NULL``) are updated in place so the
    seed can be rerun safely after adding new exercises or corrections.
    """
    path = _exercise_data_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    data: list[dict[str, Any]] = raw.get("exercises", [])

    inserted = 0
    updated = 0
    for item in data:
        slug = item["slug"]
        existing = db.scalar(
            select(ExerciseLibrary).where(
                ExerciseLibrary.slug == slug, ExerciseLibrary.user_id.is_(None)
            )
        )
        if existing is None:
            db.add(
                ExerciseLibrary(
                    slug=slug,
                    name=item["name"],
                    primary_muscle_group=item.get("primary_muscle_group"),
                    equipment=item.get("equipment"),
                    movement_type=item.get("movement_type"),
                    unit_mode=item.get("unit_mode", "reps_weight"),
                    is_custom=False,
                    user_id=None,
                )
            )
            inserted += 1
        else:
            existing.name = item["name"]
            existing.primary_muscle_group = item.get("primary_muscle_group")
            existing.equipment = item.get("equipment")
            existing.movement_type = item.get("movement_type")
            existing.unit_mode = item.get("unit_mode", "reps_weight")
            updated += 1

    db.commit()
    log.info("seeded_exercises: inserted=%d updated=%d total=%d", inserted, updated, len(data))
    return len(data)


def run_all() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        seed_exercises(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_all()
