"""Base SQLAlchemy model."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


def _utcnow() -> datetime:
    return datetime.now(UTC)
