"""Script database model."""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ARRAY, JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, _utcnow
from app.models.types import JsonObject


class ScriptModel(Base):
    """Ordered sequence of command steps."""

    __tablename__ = "scripts"

    __table_args__ = (
        Index("ix_scripts_name", "name", unique=True),
        Index("ix_scripts_tags", "tags", postgresql_using="gin"),
        Index("ix_scripts_template_pack_id", "template_pack_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[JsonObject]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(100)).with_variant(JSON(), "sqlite"), nullable=True, default=list
    )
    template_pack_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("template_packs.id", ondelete="SET NULL"), nullable=True
    )  # noqa: E501
    timeout: Mapped[int] = mapped_column(
        sa.Integer, default=30, nullable=False, server_default="30"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=sa.func.now(),
    )
