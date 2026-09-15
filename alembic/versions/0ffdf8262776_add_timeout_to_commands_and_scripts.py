"""add timeout to commands and scripts

Revision ID: 0ffdf8262776
Revises: h4i5j6k7l8m9
Create Date: 2026-09-07 13:34:03.006031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ffdf8262776'
down_revision: Union[str, Sequence[str], None] = 'h4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add timeout to commands and scripts (unified default 30, 1..3600)."""
    with op.batch_alter_table("commands", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("timeout", sa.Integer(), nullable=False, server_default="30")
        )
    with op.batch_alter_table("scripts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("timeout", sa.Integer(), nullable=False, server_default="30")
        )
    with op.batch_alter_table("script_executions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("timeout", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove timeout columns."""
    with op.batch_alter_table("script_executions", schema=None) as batch_op:
        batch_op.drop_column("timeout")
    with op.batch_alter_table("scripts", schema=None) as batch_op:
        batch_op.drop_column("timeout")
    with op.batch_alter_table("commands", schema=None) as batch_op:
        batch_op.drop_column("timeout")
