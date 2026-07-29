"""add persistent script schedules

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-07-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "l2m3n4o5p6q7"
down_revision: str | Sequence[str] | None = "k1l2m3n4o5p6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the persistent scheduler source-of-truth table."""
    op.create_table(
        "script_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("script_id", sa.Uuid(), nullable=False),
        sa.Column("cron", sa.String(length=60), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("node_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("misfire_grace_seconds", sa.Integer(), nullable=False),
        sa.Column("operational_state", sa.String(length=50), nullable=False),
        sa.Column("last_error_type", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["script_id"], ["scripts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_script_schedules_script_id",
        "script_schedules",
        ["script_id"],
        unique=True,
    )
    op.create_index(
        "ix_script_schedules_enabled",
        "script_schedules",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    """Remove persistent script schedules."""
    op.drop_index("ix_script_schedules_enabled", table_name="script_schedules")
    op.drop_index("ix_script_schedules_script_id", table_name="script_schedules")
    op.drop_table("script_schedules")
