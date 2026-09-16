"""Favorite API schemas."""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import SafeName


class FavoriteCreate(BaseModel):
    """Request body for creating a favorite (shortcut) to any entity."""

    target_type: str
    target_id: str
    name: SafeName | None = None
    note: str | None = None


class FavoriteUpdate(BaseModel):
    """Patch favorite note/name."""

    name: SafeName | None = None
    note: str | None = None


class FavoriteResponse(BaseModel):
    """Favorite response schema."""

    id: str
    target_type: str
    target_id: str
    name: str | None
    note: str | None
    created_at: datetime
