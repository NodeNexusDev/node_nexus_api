"""Add remaining CheckConstraints.

Revision ID: h4i5j6k7l8m9
Revises: g3h4i5j6k7l8
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "h4i5j6k7l8m9"
down_revision: str | Sequence[str] | None = "g3h4i5j6k7l8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Normalize before constraint
    op.execute(
        sa.text(  # noqa: E501
            "UPDATE nodes SET connection_type='ssh' WHERE connection_type != 'ssh'"
        )
    )
    op.execute(
        sa.text(  # noqa: E501
            "UPDATE script_schedules SET operational_state='registered' "
            "WHERE operational_state NOT IN ('registered','pending_registration')"
        )
    )
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.create_check_constraint(
            "chk_nodes_connection_type",
            condition="connection_type = 'ssh'",
        )
    with op.batch_alter_table("script_schedules") as batch_op:
        batch_op.create_check_constraint(
            "chk_script_schedules_operational_state",
            condition="operational_state IN ('registered', 'pending_registration')",
        )


def downgrade() -> None:
    with op.batch_alter_table("script_schedules") as batch_op:
        batch_op.drop_constraint(
            "chk_script_schedules_operational_state", type_="check"
        )
    with op.batch_alter_table("nodes") as batch_op:
        batch_op.drop_constraint("chk_nodes_connection_type", type_="check")
