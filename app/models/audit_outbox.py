"""Transactional audit outbox model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class AuditOutboxModel(Base):
    """Durable delivery state for one logical audit event."""

    __tablename__ = "audit_outbox"
    __table_args__ = (
        Index(
            "ix_audit_outbox_delivery",
            "status",
            "next_attempt_at",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
