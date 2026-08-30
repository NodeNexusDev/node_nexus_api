"""Template installation model for 2.0."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class TemplateInstallationModel(Base):
    """Link pack -> created entity (command/script)."""

    __tablename__ = "template_installations"
    __table_args__ = (
        Index("ix_template_installations_pack_id", "pack_id"),
        Index("ix_template_installations_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pack_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
