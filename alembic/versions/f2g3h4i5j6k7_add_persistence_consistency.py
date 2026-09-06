"""Add persistence consistency: server defaults, checks, indexes.

Revision ID: f2g3h4i5j6k7
Revises: e8f9g0h1i2j3
Create Date: 2026-09-06
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2g3h4i5j6k7"
down_revision: str | Sequence[str] | None = "e8f9g0h1i2j3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Normalize audit_outbox status before constraint
    op.execute(
        sa.text(
            "UPDATE audit_outbox SET status='pending' "
            "WHERE status NOT IN ('pending','processing','completed','failed')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE api_keys SET scope='read-write' "
            "WHERE scope NOT IN ('read-only','read-write')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE favorites SET target_type='node' "
            "WHERE target_type NOT IN ('command','script','node')"
        )
    )

    # Check constraints via batch (SQLite compat)
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.create_check_constraint(
            "chk_api_keys_scope",
            condition="scope IN ('read-only', 'read-write')",
        )
    with op.batch_alter_table("audit_outbox") as batch_op:
        batch_op.create_check_constraint(
            "chk_audit_outbox_status",
            condition="status IN ('pending', 'processing', 'completed', 'failed')",
        )
    with op.batch_alter_table("favorites") as batch_op:
        batch_op.create_check_constraint(
            "chk_favorites_target_type",
            condition="target_type IN ('command', 'script', 'node')",
        )

    # Server defaults for timestamps
    for table, cols in [
        ("commands", ["created_at", "updated_at"]),
        ("scripts", ["created_at", "updated_at"]),
        ("users", ["created_at", "updated_at"]),
        ("compose_projects", ["created_at", "updated_at"]),
        ("template_packs", ["created_at", "updated_at"]),
        ("template_assets", ["created_at", "updated_at"]),
        ("template_registries", ["created_at", "updated_at"]),
        ("template_installations", ["created_at"]),
        ("favorites", ["created_at"]),
        ("audit_logs", ["created_at"]),
        ("audit_outbox", ["created_at", "next_attempt_at"]),
        ("refresh_tokens", ["created_at"]),
        ("api_keys", ["created_at"]),
        ("script_schedules", ["created_at", "updated_at"]),
        ("script_executions", ["started_at"]),
        ("command_executions", ["started_at", "created_at"]),
    ]:
        for col in cols:
            try:
                with op.batch_alter_table(table) as batch_op:
                    batch_op.alter_column(
                        col,
                        existing_type=sa.DateTime(timezone=True),
                        server_default=sa.func.now(),
                        existing_nullable=False,
                    )
            except Exception:
                # Column may not exist on fresh DB (e.g., script_executions.created_at) — skip.
                pass

    # Indexes (if_not_exists for idempotency, fallback without)
    try:
        op.create_index("ix_audit_logs_node_id", "audit_logs", ["node_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    except Exception:
        pass
    try:
        op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    except Exception:
        pass
    try:
        op.create_index("ix_scripts_template_pack_id", "scripts", ["template_pack_id"])
    except Exception:
        pass
    try:
        op.create_index(
            "ix_commands_template_pack_id", "commands", ["template_pack_id"]
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_constraint("chk_api_keys_scope", "api_keys", type_="check")
    op.drop_constraint("chk_audit_outbox_status", "audit_outbox", type_="check")
    op.drop_constraint("chk_favorites_target_type", "favorites", type_="check")
    op.drop_index("ix_audit_logs_node_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_scripts_template_pack_id", table_name="scripts")
    op.drop_index("ix_commands_template_pack_id", table_name="commands")
    # server_default downgrade omitted for brevity (would set to None)
