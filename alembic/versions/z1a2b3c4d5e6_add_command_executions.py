"""add command_executions table

Revision ID: z1a2b3c4d5e6
Revises: l2m3n4o5p6q7
Create Date: 2026-08-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the command execution history table."""
    op.create_table(
        "command_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("command_id", sa.Uuid(), nullable=True),
        sa.Column("command_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("stdout_bytes", sa.Integer(), nullable=True),
        sa.Column("stderr_bytes", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_id"], ["nodes.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["command_id"], ["commands.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_command_executions_node_id", "command_executions", ["node_id"]
    )
    op.create_index(
        "ix_command_executions_created_at",
        "command_executions",
        ["created_at"],
    )
    op.create_index(
        "ix_command_executions_fingerprint",
        "command_executions",
        ["command_fingerprint"],
    )


def downgrade() -> None:
    """Remove the command execution history table."""
    op.drop_index(
        "ix_command_executions_fingerprint", table_name="command_executions"
    )
    op.drop_index(
        "ix_command_executions_created_at", table_name="command_executions"
    )
    op.drop_index(
        "ix_command_executions_node_id", table_name="command_executions"
    )
    op.drop_table("command_executions")
