"""Template pack model for 2.0."""

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, JSON, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class TemplatePackModel(Base):
    """Template pack (from GitHub or local)."""

    __tablename__ = "template_packs"
    __table_args__ = (
        Index("ix_template_packs_registry_id", "registry_id"),
        Index(
            "ix_template_packs_registry_pack",
            "registry_id",
            "pack_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    registry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    pack_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)).with_variant(JSON(), "sqlite"), nullable=True, default=list
    )
    manifest_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    readme: Mapped[str | None] = mapped_column(Text, nullable=True)
    installed_version: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    installed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
