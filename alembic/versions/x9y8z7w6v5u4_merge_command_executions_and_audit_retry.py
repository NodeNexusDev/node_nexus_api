"""merge command_executions and audit_outbox_retry heads

Revision ID: x9y8z7w6v5u4
Revises: n4o5p6q7r8s9, z1a2b3c4d5e6
Create Date: 2026-08-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "x9y8z7w6v5u4"
down_revision: str | Sequence[str] | None = ("n4o5p6q7r8s9", "z1a2b3c4d5e6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Resolve multiple migration heads."""
    pass


def downgrade() -> None:
    """No-op merge migration downgrade."""
    pass
