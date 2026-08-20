"""Favorite entity model."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FavoriteModel(Base):
    """A user bookmark for a command or script."""

    __tablename__ = "favorites"
    __table_args__ = (Index("ix_favorites_target", "target_type", "target_id"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
