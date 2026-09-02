"""Compose project model for 2.0."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow


class ComposeProjectModel(Base):
    """Persisted compose project per node."""

    __tablename__ = "compose_projects"
    __table_args__ = (
        Index("ix_compose_projects_node_id", "node_id"),
        Index("ix_compose_projects_template_pack_id", "template_pack_id"),
        Index(
            "ix_compose_projects_node_project",
            "node_id",
            "project_name",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_name: Mapped[str] = mapped_column(String(100), nullable=False)
    compose: Mapped[str] = mapped_column(Text, nullable=False)
    env: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    template_pack_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
