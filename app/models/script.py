"""Script database model."""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class ScriptModel(Base):
    """Ordered sequence of command steps."""

    __tablename__ = "scripts"

    __table_args__ = (
        Index("ix_scripts_name", "name", unique=True),
        Index("ix_scripts_tags", "tags", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[dict]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)).with_variant(JSON(), "sqlite"), nullable=True, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
