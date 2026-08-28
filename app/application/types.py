"""Shared transport- and persistence-neutral application value types."""

from datetime import datetime
from uuid import UUID

from app.core.types import JsonObject, JsonScalar, JsonValue

__all__ = ["JsonObject", "JsonScalar", "JsonValue", "PersistenceObject"]

type PersistenceScalar = JsonScalar | UUID | datetime
type PersistenceValue = (
    PersistenceScalar | list[PersistenceValue] | dict[str, PersistenceValue]
)
type PersistenceObject = dict[str, PersistenceValue]
