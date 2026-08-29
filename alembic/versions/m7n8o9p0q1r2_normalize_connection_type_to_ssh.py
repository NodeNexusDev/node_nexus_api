"""Normalize legacy connection_type values to ssh.

Revision ID: m7n8o9p0q1r2
Revises: w6x7y8z9a0b1
Create Date: 2026-08-29

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m7n8o9p0q1r2"
down_revision: str | None = "w6x7y8z9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Migrate docker/proxmox connection_type to ssh, preserving has_docker."""
    # Ensure has_docker is true for legacy docker nodes before changing type
    op.execute(
        sa.text("UPDATE nodes SET has_docker = true WHERE connection_type = 'docker'")  # noqa: E501
    )
    op.execute(
        sa.text("UPDATE nodes SET connection_type = 'ssh' WHERE connection_type IN ('docker', 'proxmox')")  # noqa: E501
    )


def downgrade() -> None:
    """Downgrade is no-op: legacy types cannot be restored reliably."""
