"""Template registry models for 2.0."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class TemplateRegistryModel(Base):
    """GitHub template registry."""

    __tablename__ = "template_registries"
    __table_args__ = (
        Index("ix_template_registries_owner_name", "owner", "name", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    github_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(
        String(100), nullable=False, default="main"
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
