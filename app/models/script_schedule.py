"""Persistent script schedule model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class ScriptScheduleModel(Base):
    """PostgreSQL source of truth for a scheduled script."""

    __tablename__ = "script_schedules"
    __table_args__ = (
        Index("ix_script_schedules_script_id", "script_id", unique=True),
        Index("ix_script_schedules_enabled", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    script_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False
    )
    cron: Mapped[str] = mapped_column(String(60), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    node_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    misfire_grace_seconds: Mapped[int] = mapped_column(Integer, default=60)
    operational_state: Mapped[str] = mapped_column(String(50), default="registered")
    last_error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
