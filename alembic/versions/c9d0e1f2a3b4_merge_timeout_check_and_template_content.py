"""merge stale command_executions branch and template content heads

Revision ID: c9d0e1f2a3b4
Revises: z1a2b3c4d5e6, a1b2c3d4e5f7
Create Date: 2026-09-17 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = ("z1a2b3c4d5e6", "a1b2c3d4e5f7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Resolve multiple migration heads."""
    pass


def downgrade() -> None:
    """No-op merge migration downgrade."""
    pass
