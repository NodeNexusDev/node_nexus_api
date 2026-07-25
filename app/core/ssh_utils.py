"""Shared SSH-related utilities for services."""

from app.core.connectors.base import ConnectorFactory
from app.core.security import decrypt


def decrypt_value(value: str | None) -> str | None:
    """Decrypt a single value if it looks encrypted."""
    if not value:
        return value
    try:
        return decrypt(value)
    except Exception:
        return value


def get_connector_factory(factory: ConnectorFactory | None) -> ConnectorFactory:
    """Get connector factory or raise if not configured."""
    if factory is None:
        raise RuntimeError("ConnectorFactory not configured")
    return factory
