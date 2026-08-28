"""Types for data which intentionally remains dynamic at external test boundaries."""

from typing import Any

type UnvalidatedJsonObject = dict[str, Any]
type UnvalidatedJsonArray = list[Any]
type UnvalidatedHttpOption = Any
