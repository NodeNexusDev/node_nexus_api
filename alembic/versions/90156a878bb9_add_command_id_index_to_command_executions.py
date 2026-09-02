"""add command_id index to command_executions

Revision ID: 90156a878bb9
Revises: b1c2d3e4f5g6
Create Date: 2026-09-02

"""

from collections.abc import Sequence

from alembic import op

revision: str = "90156a878bb9"
down_revision: str | Sequence[str] | None = "b1c2d3e4f5g6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_command_executions_command_id",
        "command_executions",
        ["command_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_command_executions_command_id",
        table_name="command_executions",
    )
