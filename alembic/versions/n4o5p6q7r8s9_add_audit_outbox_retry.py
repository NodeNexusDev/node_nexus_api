"""Add retry scheduling to the audit outbox.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n4o5p6q7r8s9"
down_revision: str | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_audit_outbox_status_created", table_name="audit_outbox")
    op.add_column(
        "audit_outbox",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_outbox_delivery",
        "audit_outbox",
        ["status", "next_attempt_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_outbox_delivery", table_name="audit_outbox")
    op.drop_column("audit_outbox", "next_attempt_at")
    op.create_index(
        "ix_audit_outbox_status_created",
        "audit_outbox",
        ["status", "created_at"],
    )
