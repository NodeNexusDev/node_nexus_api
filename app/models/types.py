"""Persistence-local JSON value types used by SQLAlchemy JSON columns."""

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

#: Execution timeout bounds in seconds, single source of truth.
#: app.core.constants re-exports these for the API layer.
TIMEOUT_MIN: int = 1
TIMEOUT_MAX: int = 3600
DEFAULT_TIMEOUT: int = 30
