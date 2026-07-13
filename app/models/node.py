"""Node database model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _default_port() -> int:
    return 22


def _default_status() -> str:
    return "active"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class NodeModel(Base):
    """Node database model."""

    __tablename__ = "nodes"
    __table_args__ = (
        Index("ix_nodes_name", "name"),
        Index("ix_nodes_host", "host"),
        Index("ix_nodes_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=_default_port)
    connection_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default=_default_status)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
