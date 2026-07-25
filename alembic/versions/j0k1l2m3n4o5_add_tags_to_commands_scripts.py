"""Add tags to commands and scripts tables.

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-07-26

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "j0k1l2m3n4o5"
down_revision: str | None = "i9j0k1l2m3n4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add tags column to commands and scripts tables."""
    op.add_column(
        "commands",
        sa.Column("tags", sa.ARRAY(sa.String(length=100)), nullable=True),
    )
    op.create_index("ix_commands_tags", "commands", ["tags"], postgresql_using="gin")

    op.add_column(
        "scripts",
        sa.Column("tags", sa.ARRAY(sa.String(length=100)), nullable=True),
    )
    op.create_index("ix_scripts_tags", "scripts", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    """Remove tags column from commands and scripts tables."""
    op.drop_index("ix_scripts_tags", postgresql_using="gin")
    op.drop_column("scripts", "tags")

    op.drop_index("ix_commands_tags", postgresql_using="gin")
    op.drop_column("commands", "tags")
