"""Node schemas for API."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class NodeCreate(BaseModel):
    """Schema for creating a node."""

    name: str
    host: str
    port: int = 22
    connection_type: str


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    connection_type: Optional[str] = None
    status: Optional[str] = None


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
