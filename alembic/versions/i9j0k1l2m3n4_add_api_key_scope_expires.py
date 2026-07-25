"""Add scope and expires_at to api_keys table.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-07-26

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "i9j0k1l2m3n4"
down_revision: str | None = "h8i9j0k1l2m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add scope and expires_at columns to api_keys."""
    op.add_column(
        "api_keys",
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="read-write"),
    )
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove scope and expires_at columns from api_keys."""
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "scope")
