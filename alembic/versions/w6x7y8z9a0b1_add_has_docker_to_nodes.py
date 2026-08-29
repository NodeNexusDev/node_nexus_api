"""Add has_docker toggle to nodes.

Revision ID: w6x7y8z9a0b1
Revises: v2w3x4y5z6a7
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "w6x7y8z9a0b1"
down_revision: str | None = "v2w3x4y5z6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add has_docker column and backfill from connection_type."""
    op.add_column(
        "nodes",
        sa.Column(
            "has_docker",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Backfill: legacy docker nodes get has_docker=true
    op.execute(
        sa.text("UPDATE nodes SET has_docker = true WHERE connection_type = 'docker'")  # noqa: E501
    )
    # For remaining rows ensure false (already default) but explicit
    op.execute(sa.text("UPDATE nodes SET has_docker = false WHERE has_docker IS NULL"))


def downgrade() -> None:
    """Remove has_docker column."""
    op.drop_column("nodes", "has_docker")
