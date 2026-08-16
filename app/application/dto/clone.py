from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CloneCommandDTO:
    command_id: uuid.UUID
    new_name: str | None = None


@dataclass(frozen=True, slots=True)
class CloneScriptDTO:
    script_id: uuid.UUID
    new_name: str | None = None
