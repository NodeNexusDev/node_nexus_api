"""add trigger and schedule_id to script_executions

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-16
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | Sequence[str] | None = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "script_executions",
        sa.Column("trigger", sa.String(20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "script_executions",
        sa.Column(
            "schedule_id",
            sa.Uuid(),
            sa.ForeignKey("script_schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_script_executions_trigger",
        "script_executions",
        ["trigger"],
    )


def downgrade() -> None:
    op.drop_index("ix_script_executions_trigger", table_name="script_executions")
    op.drop_column("script_executions", "schedule_id")
    op.drop_column("script_executions", "trigger")
