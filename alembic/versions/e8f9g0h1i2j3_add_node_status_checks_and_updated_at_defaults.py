"""Add CHECK constraints for node status and updated_at defaults.

Revision ID: e8f9g0h1i2j3
Revises: 90156a878bb9
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8f9g0h1i2j3"
down_revision: str | Sequence[str] | None = "90156a878bb9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Normalize dirty data before adding constraints (defensive)
    op.execute(
        sa.text(
            "UPDATE nodes SET status='active' "  # noqa: E501
            "WHERE status NOT IN ('active','unreachable','error')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE node_status_history SET old_status=NULL "  # noqa: E501
            "WHERE old_status IS NOT NULL AND old_status NOT IN "  # noqa: E501
            "('active','unreachable','error')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE node_status_history SET new_status='active' "  # noqa: E501
            "WHERE new_status NOT IN ('active','unreachable','error')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE node_status_history SET source='connectivity_check' "  # noqa: E501
            "WHERE source NOT IN ('connectivity_check','manual_update')"
        )
    )

    # Add CHECK constraints — use batch for SQLite compatibility
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.create_check_constraint(
            "chk_nodes_status",
            condition="status IN ('active', 'unreachable', 'error')",
        )
    with op.batch_alter_table("node_status_history") as batch_op:
        batch_op.create_check_constraint(
            "chk_nsh_old_status",
            condition="old_status IS NULL OR old_status IN "  # noqa: E501
            "('active', 'unreachable', 'error')",
        )
        batch_op.create_check_constraint(
            "chk_nsh_new_status",
            condition="new_status IN ('active', 'unreachable', 'error')",
        )
        batch_op.create_check_constraint(
            "chk_nsh_source",
            condition="source IN ('connectivity_check', 'manual_update')",
        )

    # Add server_default for nodes created_at/updated_at and history changed_at
    # These are idempotent if already present
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            existing_nullable=False,
        )
    with op.batch_alter_table("node_status_history") as batch_op:
        batch_op.alter_column(
            "changed_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_constraint("chk_nodes_status", type_="check")
    with op.batch_alter_table("node_status_history") as batch_op:
        batch_op.drop_constraint("chk_nsh_old_status", type_="check")
        batch_op.drop_constraint("chk_nsh_new_status", type_="check")
        batch_op.drop_constraint("chk_nsh_source", type_="check")
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
            existing_nullable=False,
        )
    with op.batch_alter_table("node_status_history") as batch_op:
        batch_op.alter_column(
            "changed_at",
            existing_type=sa.DateTime(timezone=True),
            server_default=None,
            existing_nullable=False,
        )
