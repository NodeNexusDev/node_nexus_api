"""Favorite API schemas."""

from datetime import datetime

from pydantic import BaseModel


class FavoriteCreate(BaseModel):
    target_type: str
    target_id: str
    name: str | None = None
    note: str | None = None


class FavoriteResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    name: str | None
    note: str | None
    created_at: datetime
