"""store pack commands/scripts content and enforce local pack_id uniqueness

Revision ID: a1b2c3d4e5f7
Revises: 1a2b3c4d5e6f
Create Date: 2026-09-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "1a2b3c4d5e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add commands/scripts JSON columns and local pack_id unique index."""
    op.add_column("template_packs", sa.Column("commands", sa.JSON(), nullable=True))
    op.add_column("template_packs", sa.Column("scripts", sa.JSON(), nullable=True))
    # The composite unique index ignores NULL registry_id (local packs).
    # Partial index enforces pack_id uniqueness for local packs.
    op.create_index(
        "uq_template_packs_local_pack_id",
        "template_packs",
        ["pack_id"],
        unique=True,
        postgresql_where=sa.text("registry_id IS NULL"),
        sqlite_where=sa.text("registry_id IS NULL"),
    )


def downgrade() -> None:
    """Drop local pack_id unique index and content columns."""
    op.drop_index("uq_template_packs_local_pack_id", table_name="template_packs")
    op.drop_column("template_packs", "scripts")
    op.drop_column("template_packs", "commands")
