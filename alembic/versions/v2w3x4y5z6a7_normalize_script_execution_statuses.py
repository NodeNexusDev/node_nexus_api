"""Normalize script execution statuses.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: str | None = "u1v2w3x4y5z6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_CONSTRAINT = "ck_script_executions_status"


def upgrade() -> None:
    """Normalize legacy values and constrain the canonical status vocabulary."""
    op.execute(
        sa.text(
            "UPDATE script_executions "
            "SET status = CASE status "
            "WHEN 'completed' THEN 'success' "
            "WHEN 'failed' THEN 'error' "
            "ELSE status END "
            "WHERE status IN ('completed', 'failed')"
        )
    )
    op.create_check_constraint(
        _STATUS_CONSTRAINT,
        "script_executions",
        "status IN ('pending', 'running', 'success', 'error', 'cancelled')",
    )


def downgrade() -> None:
    """Restore the legacy terminal values and remove the status constraint."""
    op.drop_constraint(
        _STATUS_CONSTRAINT,
        "script_executions",
        type_="check",
    )
    op.execute(
        sa.text(
            "UPDATE script_executions "
            "SET status = CASE status "
            "WHEN 'success' THEN 'completed' "
            "WHEN 'error' THEN 'failed' "
            "ELSE status END "
            "WHERE status IN ('success', 'error')"
        )
    )
