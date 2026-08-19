"""add passphrase column to nodes

Revision ID: b7c8d9e0f1a2
Revises: x9y8z7w6v5u4, f5g6h7i8j9k0
Create Date: 2026-08-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = ("x9y8z7w6v5u4", "f5g6h7i8j9k0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add passphrase column to nodes table."""
    op.add_column("nodes", sa.Column("passphrase", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove passphrase column from nodes table."""
    op.drop_column("nodes", "passphrase")
