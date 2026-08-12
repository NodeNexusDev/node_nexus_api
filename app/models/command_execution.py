"""Command execution history database model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class CommandExecutionModel(Base):
    """Result of a single command executed on one node."""

    __tablename__ = "command_executions"

    __table_args__ = (
        Index("ix_command_executions_node_id", "node_id"),
        Index("ix_command_executions_created_at", "created_at"),
        Index("ix_command_executions_fingerprint", "command_fingerprint"),
        Index("ix_command_executions_batch_id", "batch_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    command_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commands.id", ondelete="SET NULL"),
        nullable=True,
    )
    command_fingerprint: Mapped[str] = mapped_column(String(64))
    exit_code: Mapped[int] = mapped_column(Integer)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stderr_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
