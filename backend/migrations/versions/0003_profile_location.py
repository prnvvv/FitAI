"""Add optional location fields to user_profiles.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("location_label", sa.String(255), nullable=True))
    op.add_column("user_profiles", sa.Column("location_lat", sa.Numeric(8, 5), nullable=True))
    op.add_column("user_profiles", sa.Column("location_lon", sa.Numeric(8, 5), nullable=True))
    op.add_column("user_profiles", sa.Column("location_timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "location_timezone")
    op.drop_column("user_profiles", "location_lon")
    op.drop_column("user_profiles", "location_lat")
    op.drop_column("user_profiles", "location_label")
