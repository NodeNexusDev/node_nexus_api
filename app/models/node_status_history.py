"""Node status history — records every status change for a node."""

from __future__ import annotations

import datetime
import uuid

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class NodeStatusHistoryModel(Base):
    __tablename__ = "node_status_history"
    __table_args__ = (
        Index("idx_nsh_node_id", "node_id"),
        Index("idx_nsh_changed_at", "changed_at"),
        sa.CheckConstraint(
            "old_status IS NULL OR old_status IN ('active', 'unreachable', 'error')",
            name="chk_nsh_old_status",
        ),
        sa.CheckConstraint(
            "new_status IN ('active', 'unreachable', 'error')",
            name="chk_nsh_new_status",
        ),
        sa.CheckConstraint(
            "source IN ('connectivity_check', 'manual_update')",
            name="chk_nsh_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    changed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=sa.func.now(),
    )
