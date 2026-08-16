"""Favorite DTOs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FavoriteCreateDTO:
    target_type: str
    target_id: uuid.UUID
    note: str | None = None


@dataclass(frozen=True, slots=True)
class FavoriteDTO:
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    note: str | None
    created_at: datetime
