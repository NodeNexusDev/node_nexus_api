"""Add FK for template and compose tables.

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2026-09-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "g3h4i5j6k7l8"
down_revision: str | Sequence[str] | None = "f2g3h4i5j6k7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Template packs registry FK
    with op.batch_alter_table("template_packs") as batch_op:
        batch_op.create_foreign_key(
            "fk_template_packs_registry_id",
            "template_registries",
            ["registry_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # Template assets pack FK
    with op.batch_alter_table("template_assets") as batch_op:
        batch_op.create_foreign_key(
            "fk_template_assets_pack_id",
            "template_packs",
            ["pack_id"],
            ["id"],
            ondelete="CASCADE",
        )
    # Template installations pack FK
    with op.batch_alter_table("template_installations") as batch_op:
        batch_op.create_foreign_key(
            "fk_template_installations_pack_id",
            "template_packs",
            ["pack_id"],
            ["id"],
            ondelete="CASCADE",
        )
    # Compose projects
    with op.batch_alter_table("compose_projects") as batch_op:
        batch_op.create_foreign_key(
            "fk_compose_projects_node_id",
            "nodes",
            ["node_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_compose_projects_template_pack_id",
            "template_packs",
            ["template_pack_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # Commands/scripts template pack FK
    with op.batch_alter_table("commands") as batch_op:
        batch_op.create_foreign_key(
            "fk_commands_template_pack_id",
            "template_packs",
            ["template_pack_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("scripts") as batch_op:
        batch_op.create_foreign_key(
            "fk_scripts_template_pack_id",
            "template_packs",
            ["template_pack_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("scripts") as batch_op:
        batch_op.drop_constraint("fk_scripts_template_pack_id", type_="foreignkey")
    with op.batch_alter_table("commands") as batch_op:
        batch_op.drop_constraint("fk_commands_template_pack_id", type_="foreignkey")
    with op.batch_alter_table("compose_projects") as batch_op:
        batch_op.drop_constraint(
            "fk_compose_projects_template_pack_id", type_="foreignkey"
        )
        batch_op.drop_constraint("fk_compose_projects_node_id", type_="foreignkey")
    with op.batch_alter_table("template_installations") as batch_op:
        batch_op.drop_constraint(
            "fk_template_installations_pack_id", type_="foreignkey"
        )
    with op.batch_alter_table("template_assets") as batch_op:
        batch_op.drop_constraint("fk_template_assets_pack_id", type_="foreignkey")
    with op.batch_alter_table("template_packs") as batch_op:
        batch_op.drop_constraint("fk_template_packs_registry_id", type_="foreignkey")
