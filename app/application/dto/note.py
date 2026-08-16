"""Note DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NoteCreateDTO:
    target_type: str
    target_id: uuid.UUID
    content: str


@dataclass(frozen=True, slots=True)
class NoteUpdateDTO:
    content: str


@dataclass(frozen=True, slots=True)
class NoteDTO:
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    content: str
    created_at: datetime
    updated_at: datetime
