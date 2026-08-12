"""add batch_id to command_executions

Revision ID: a1b2c3d4e5f6
Revises: x9y8z7w6v5u4
Create Date: 2026-08-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7a8c9d0e1f2"
down_revision: str | Sequence[str] | None = "x9y8z7w6v5u4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add batch_id column for grouping bulk command executions."""
    op.add_column(
        "command_executions",
        sa.Column("batch_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_command_executions_batch_id",
        "command_executions",
        ["batch_id"],
    )


def downgrade() -> None:
    """Remove batch_id column."""
    op.drop_index(
        "ix_command_executions_batch_id", table_name="command_executions"
    )
    op.drop_column("command_executions", "batch_id")
