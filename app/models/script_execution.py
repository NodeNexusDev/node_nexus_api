"""Script execution database model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


def _default_status() -> str:
    return "pending"


class ScriptExecutionModel(Base):
    """Result of a single script run on one node."""

    __tablename__ = "script_executions"

    __table_args__ = (
        Index("ix_script_executions_script_id", "script_id"),
        Index("ix_script_executions_node_id", "node_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE")
    )
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True
    )
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=_default_status)
    steps: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
