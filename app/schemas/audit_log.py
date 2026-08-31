"""Audit log schemas for API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class AuditStatsBucket(BaseModel):
    """Single time bucket for audit stats grouping."""

    bucket: str = Field(description="Bucket label, e.g. 2026-08-30 or 2026-08-30T10:00")
    count: int = Field(description="Number of audit entries in bucket")


class AuditStatsResponse(BaseModel):
    """Aggregate audit stats without group_by."""

    total: int
    buckets: list[AuditStatsBucket] = Field(default_factory=list)


class AuditBucketsResponse(BaseModel):
    """Buckets response when group_by is present."""

    total: int
    buckets: list[AuditStatsBucket]
