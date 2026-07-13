"""Audit log schemas for API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

AuditAction = Literal[
    "create", "update", "delete", "check", "execute", "execute_failed"
]


class AuditLogResponse(BaseModel):
    """Schema for audit log response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: uuid.UUID | None
    action: str
    user: str | None
    details: str | None
    created_at: datetime
