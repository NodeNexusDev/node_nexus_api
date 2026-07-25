"""Add docker_host column to nodes table.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-25

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "h8i9j0k1l2m3"
down_revision: str | None = "g7h8i9j0k1l2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add docker_host column to nodes table."""
    op.add_column(
        "nodes",
        sa.Column("docker_host", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Remove docker_host column from nodes table."""
    op.drop_column("nodes", "docker_host")
