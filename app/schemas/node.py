"""Node schemas for API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NodeCreate(BaseModel):
    """Schema for creating a node."""

    name: str
    host: str
    port: int = 22
    connection_type: str


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    name: str | None = None
    host: str | None = None
    port: int | None = None
    connection_type: str | None = None
    status: str | None = None


class NodeResponse(BaseModel):
    """Schema for node response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    host: str
    port: int
    connection_type: str
    status: str
    created_at: datetime
    updated_at: datetime
