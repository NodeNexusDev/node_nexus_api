"""Shared transport- and persistence-neutral application value types."""

from datetime import datetime
from uuid import UUID

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type PersistenceScalar = JsonScalar | UUID | datetime
type PersistenceValue = (
    PersistenceScalar | list[PersistenceValue] | dict[str, PersistenceValue]
)
type PersistenceObject = dict[str, PersistenceValue]
