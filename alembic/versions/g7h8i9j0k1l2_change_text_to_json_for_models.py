"""Change Text columns to JSON for command parameters, script steps, and execution data.

Revision ID: g7h8i9j0k1l2
Revises: f7a8b9c0d1e2
Create Date: 2026-07-19

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "g7h8i9j0k1l2"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # commands.parameters: Text → JSON
    op.alter_column(
        "commands",
        "parameters",
        type_=sa.JSON(),
        postgresql_using="parameters::json",
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    # scripts.steps: Text → JSON
    op.alter_column(
        "scripts",
        "steps",
        type_=sa.JSON(),
        postgresql_using="steps::json",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    # script_executions.params: Text → JSON
    op.alter_column(
        "script_executions",
        "params",
        type_=sa.JSON(),
        postgresql_using="params::json",
        existing_type=sa.Text(),
        existing_nullable=True,
    )

    # script_executions.steps: Text → JSON
    op.alter_column(
        "script_executions",
        "steps",
        type_=sa.JSON(),
        postgresql_using="steps::json",
        existing_type=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    # commands.parameters: JSON → Text
    op.alter_column(
        "commands",
        "parameters",
        type_=sa.Text(),
        existing_type=sa.JSON(),
        existing_nullable=True,
    )

    # scripts.steps: JSON → Text
    op.alter_column(
        "scripts",
        "steps",
        type_=sa.Text(),
        existing_type=sa.JSON(),
        existing_nullable=False,
    )

    # script_executions.params: JSON → Text
    op.alter_column(
        "script_executions",
        "params",
        type_=sa.Text(),
        existing_type=sa.JSON(),
        existing_nullable=True,
    )

    # script_executions.steps: JSON → Text
    op.alter_column(
        "script_executions",
        "steps",
        type_=sa.Text(),
        existing_type=sa.JSON(),
        existing_nullable=True,
    )
