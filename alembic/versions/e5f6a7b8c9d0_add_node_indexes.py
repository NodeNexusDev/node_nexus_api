"""add indexes to nodes table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-14 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index('ix_nodes_name', 'nodes', ['name'])
    op.create_index('ix_nodes_host', 'nodes', ['host'])
    op.create_index('ix_nodes_status', 'nodes', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_nodes_status')
    op.drop_index('ix_nodes_host')
    op.drop_index('ix_nodes_name')
