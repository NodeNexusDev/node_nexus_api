"""Command database model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ARRAY, JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class CommandModel(Base):
    """Saved reusable command template."""

    __tablename__ = "commands"

    __table_args__ = (
        Index("ix_commands_name", "name", unique=True),
        Index("ix_commands_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    command: Mapped[str] = mapped_column(Text)
    parameters: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)).with_variant(JSON(), "sqlite"), nullable=True, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
