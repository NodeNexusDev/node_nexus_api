"""Template asset model for 2.0."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class TemplateAssetModel(Base):
    """Asset file for a template pack."""

    __tablename__ = "template_assets"
    __table_args__ = (
        Index("ix_template_assets_pack_id", "pack_id"),
        Index("ix_template_assets_pack_path", "pack_id", "path", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
