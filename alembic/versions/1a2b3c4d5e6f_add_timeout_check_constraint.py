"""add timeout check constraint 1..3600

Revision ID: 1a2b3c4d5e6f
Revises: 0ffdf8262776
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "0ffdf8262776"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CheckConstraint timeout 1..3600 with postgresql_not_valid for existing rows."""
    with op.batch_alter_table("commands", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_commands_timeout",
            {"condition": "timeout >= 1 AND timeout <= 3600", "postgresql_not_valid": True},
        )
    with op.batch_alter_table("scripts", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_scripts_timeout",
            {"condition": "timeout >= 1 AND timeout <= 3600", "postgresql_not_valid": True},
        )
    # Validate constraints after creation (PostgreSQL only, no-op on SQLite)
    try:
        op.execute("ALTER TABLE commands VALIDATE CONSTRAINT ck_commands_timeout")
        op.execute("ALTER TABLE scripts VALIDATE CONSTRAINT ck_scripts_timeout")
    except Exception:
        pass


def downgrade() -> None:
    """Remove timeout check constraints."""
    with op.batch_alter_table("scripts", schema=None) as batch_op:
        batch_op.drop_constraint("ck_scripts_timeout", type_="check")
    with op.batch_alter_table("commands", schema=None) as batch_op:
        batch_op.drop_constraint("ck_commands_timeout", type_="check")
