"""add SSH credentials to node

Revision ID: a1b2c3d4e5f6
Revises: 6520978a4881
Create Date: 2026-07-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6520978a4881'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('nodes', sa.Column('username', sa.String(length=255), nullable=True))
    op.add_column('nodes', sa.Column('ssh_key', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('nodes', 'ssh_key')
    op.drop_column('nodes', 'username')
