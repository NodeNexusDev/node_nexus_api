"""add node_status_history table

Revision ID: d1e2f3a4b5c6
Revises: b7a8c9d0e1f2
Create Date: 2026-08-16
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "b7a8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "node_status_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "node_id",
            sa.Uuid(),
            sa.ForeignKey("nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("old_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_nsh_node_id", "node_status_history", ["node_id"])
    op.create_index("idx_nsh_changed_at", "node_status_history", ["changed_at"])


def downgrade() -> None:
    op.drop_index("idx_nsh_changed_at", table_name="node_status_history")
    op.drop_index("idx_nsh_node_id", table_name="node_status_history")
    op.drop_table("node_status_history")
