"""add height metric exercise library and planned sessions

Revision ID: 0cf16f5439a2
Revises: 0003
Create Date: 2026-10-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0cf16f5439a2"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())

NEW_MEASUREMENT_TYPES = [
    "weight",
    "height",
    "body_fat_percent",
    "chest",
    "waist",
    "hips",
    "arm",
    "thigh",
    "neck",
    "sleep_hours",
    "water",
    "steps",
    "resting_heart_rate",
    "mood",
    "energy",
]


def _check_sql(values: list[str]) -> str:
    quoted = ", ".join(f"'{v}'::character varying" for v in values)
    return f"type::text = ANY (ARRAY[{quoted}]::text[])"


def upgrade() -> None:
    # Widen the measurements.type check constraint to include new metric types.
    op.drop_constraint("ck_measurements_measurement_type", "measurements")
    op.create_check_constraint(
        "ck_measurements_measurement_type",
        "measurements",
        sa.text(_check_sql(NEW_MEASUREMENT_TYPES)),
    )

    # Canonical + custom exercise library.
    op.create_table(
        "exercise_library",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("primary_muscle_group", sa.String(length=100), nullable=True),
        sa.Column("equipment", sa.String(length=100), nullable=True),
        sa.Column("movement_type", sa.String(length=50), nullable=True),
        sa.Column("unit_mode", sa.String(length=50), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_exercise_library"),
        sa.Index("ix_exercise_library_slug_user", "slug", "user_id", unique=True),
        sa.Index("ix_exercise_library_user", "user_id"),
    )

    # Planned sessions and their exercises.
    op.create_table(
        "planned_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("day_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("completed_session_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["completed_session_id"], ["workout_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_planned_sessions"),
        sa.Index("ix_planned_sessions_user_date", "user_id", "planned_date"),
    )

    op.create_table(
        "planned_exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planned_session_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("exercise_name", sa.String(length=200), nullable=False),
        sa.Column("target_sets", sa.Integer(), nullable=True),
        sa.Column("target_reps", sa.Integer(), nullable=True),
        sa.Column("target_weight", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("target_weight_unit", sa.String(length=10), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("distance_meters", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["planned_session_id"], ["planned_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_planned_exercises"),
        sa.Index("ix_planned_exercises_session", "planned_session_id"),
    )


def downgrade() -> None:
    op.drop_table("planned_exercises")
    op.drop_table("planned_sessions")
    op.drop_table("exercise_library")

    op.drop_constraint("ck_measurements_measurement_type", "measurements")
    op.create_check_constraint(
        "ck_measurements_measurement_type",
        "measurements",
        sa.text(
            _check_sql(
                [
                    "weight",
                    "body_fat_percent",
                    "chest",
                    "waist",
                    "hips",
                    "arm",
                    "thigh",
                    "neck",
                ]
            )
        ),
    )
