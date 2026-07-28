"""make node names unique

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-07-28 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: str | Sequence[str] | None = "j0k1l2m3n4o5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Replace the non-unique node-name index with a unique index.

    PostgreSQL intentionally aborts with a duplicate-key diagnostic if existing
    rows contain duplicate names; operators must resolve ambiguous names first.
    """
    op.drop_index("ix_nodes_name", table_name="nodes")
    op.create_index("ix_nodes_name", "nodes", ["name"], unique=True)


def downgrade() -> None:
    """Restore the non-unique node-name index."""
    op.drop_index("ix_nodes_name", table_name="nodes")
    op.create_index("ix_nodes_name", "nodes", ["name"], unique=False)
