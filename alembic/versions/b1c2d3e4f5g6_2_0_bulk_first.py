"""2.0 bulk-first: add description, template packs, compose, drop notes

Revision ID: b1c2d3e4f5g6
Revises: m7n8o9p0q1r2
Create Date: 2026-08-31

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "b1c2d3e4f5g6"
down_revision = "m7n8o9p0q1r2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nodes.description
    op.add_column("nodes", sa.Column("description", sa.Text(), nullable=True))

    # commands/scripts template_pack_id
    op.add_column(
        "commands", sa.Column("template_pack_id", UUID(as_uuid=True), nullable=True)
    )
    op.create_index(
        "ix_commands_template_pack_id", "commands", ["template_pack_id"]
    )
    op.add_column(
        "scripts", sa.Column("template_pack_id", UUID(as_uuid=True), nullable=True)
    )
    op.create_index(
        "ix_scripts_template_pack_id", "scripts", ["template_pack_id"]
    )

    # template_registries
    op.create_table(
        "template_registries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("github_token_encrypted", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(100), nullable=False, server_default="main"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_template_registries_owner_name",
        "template_registries",
        ["owner", "name"],
        unique=True,
    )

    # template_packs
    op.create_table(
        "template_packs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("registry_id", UUID(as_uuid=True), nullable=True),
        sa.Column("pack_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("manifest_sha", sa.String(64), nullable=True),
        sa.Column("readme", sa.Text(), nullable=True),
        sa.Column("installed_version", sa.String(50), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_template_packs_registry_id", "template_packs", ["registry_id"]
    )
    op.create_index(
        "ix_template_packs_registry_pack",
        "template_packs",
        ["registry_id", "pack_id"],
        unique=True,
    )

    # template_assets
    op.create_table(
        "template_assets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pack_id", UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_template_assets_pack_id", "template_assets", ["pack_id"])
    op.create_index(
        "ix_template_assets_pack_path",
        "template_assets",
        ["pack_id", "path"],
        unique=True,
    )

    # template_installations
    op.create_table(
        "template_installations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pack_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_template_installations_pack_id", "template_installations", ["pack_id"]
    )
    op.create_index(
        "ix_template_installations_entity",
        "template_installations",
        ["entity_type", "entity_id"],
    )

    # compose_projects
    op.create_table(
        "compose_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_name", sa.String(100), nullable=False),
        sa.Column("compose", sa.Text(), nullable=False),
        sa.Column("env", sa.JSON(), nullable=True),
        sa.Column("template_pack_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_compose_projects_node_id", "compose_projects", ["node_id"]
    )
    op.create_index(
        "ix_compose_projects_template_pack_id",
        "compose_projects",
        ["template_pack_id"],
    )
    op.create_index(
        "ix_compose_projects_node_project",
        "compose_projects",
        ["node_id", "project_name"],
        unique=True,
    )

    # drop notes
    op.drop_index("ix_notes_target", table_name="notes")
    op.drop_table("notes")


def downgrade() -> None:
    op.create_table(
        "notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notes_target", "notes", ["target_type", "target_id"])

    op.drop_index("ix_compose_projects_node_project", table_name="compose_projects")
    op.drop_index("ix_compose_projects_template_pack_id", table_name="compose_projects")
    op.drop_index("ix_compose_projects_node_id", table_name="compose_projects")
    op.drop_table("compose_projects")

    op.drop_index("ix_template_installations_entity", table_name="template_installations")
    op.drop_index("ix_template_installations_pack_id", table_name="template_installations")
    op.drop_table("template_installations")

    op.drop_index("ix_template_assets_pack_path", table_name="template_assets")
    op.drop_index("ix_template_assets_pack_id", table_name="template_assets")
    op.drop_table("template_assets")

    op.drop_index("ix_template_packs_registry_pack", table_name="template_packs")
    op.drop_index("ix_template_packs_registry_id", table_name="template_packs")
    op.drop_table("template_packs")

    op.drop_index("ix_template_registries_owner_name", table_name="template_registries")
    op.drop_table("template_registries")

    op.drop_index("ix_scripts_template_pack_id", table_name="scripts")
    op.drop_column("scripts", "template_pack_id")

    op.drop_index("ix_commands_template_pack_id", table_name="commands")
    op.drop_column("commands", "template_pack_id")

    op.drop_column("nodes", "description")
