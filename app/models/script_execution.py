"""Script execution database model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow
from app.models.types import JsonObject


def _default_status() -> str:
    return "pending"


class ScriptExecutionModel(Base):
    """Result of a single script run on one node."""

    __tablename__ = "script_executions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'error', 'cancelled')",
            name="ck_script_executions_status",
        ),
        Index("ix_script_executions_script_id", "script_id"),
        Index("ix_script_executions_node_id", "node_id"),
        Index("ix_script_executions_trigger", "trigger"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE")
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True
    )
    params: Mapped[JsonObject | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=_default_status)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("script_schedules.id", ondelete="SET NULL"), nullable=True
    )
    steps: Mapped[list[JsonObject] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
