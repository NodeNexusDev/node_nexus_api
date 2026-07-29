"""add transactional audit outbox

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-07-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m3n4o5p6q7r8"
down_revision: str | Sequence[str] | None = "l2m3n4o5p6q7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable audit event delivery state."""
    op.create_table(
        "audit_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_type", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_outbox_status_created",
        "audit_outbox",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the audit outbox."""
    op.drop_index("ix_audit_outbox_status_created", table_name="audit_outbox")
    op.drop_table("audit_outbox")
