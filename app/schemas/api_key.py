"""Pydantic schemas for API keys."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(..., min_length=1, max_length=255)
    scope: Literal["read-only", "read-write"] = "read-write"


class APIKeyCreated(BaseModel):
    """Schema returned after creating an API key (includes plain key once)."""

    id: uuid.UUID
    name: str
    key: str
    key_prefix: str
    created_at: datetime


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    scope: Literal["read-only", "read-write"] | None = None
    expires_at: datetime | None = None


class APIKeyResponse(BaseModel):
    """Schema for API key info (without the full key)."""

    id: uuid.UUID
    name: str
    key_prefix: str
    is_active: bool
    scope: Literal["read-only", "read-write"]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class APIKeyList(BaseModel):
    """Paginated list of API keys."""

    items: list[APIKeyResponse]
    total: int
