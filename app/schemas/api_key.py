"""Pydantic schemas for API keys."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255)


class APIKeyCreated(BaseModel):
    """Schema returned after creating an API key (includes plain key once)."""

    id: uuid.UUID
    name: str
    key: str
    key_prefix: str
    created_at: datetime


class APIKeyResponse(BaseModel):
    """Schema for API key info (without the full key)."""

    id: uuid.UUID
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class APIKeyList(BaseModel):
    """Paginated list of API keys."""

    items: list[APIKeyResponse]
    total: int
