"""Script execution schemas for API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ScriptExecutionResponse(BaseModel):
    """Schema for a single script execution record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    script_id: uuid.UUID
    node_id: uuid.UUID | None
    params: dict[str, Any] | None
    status: str
    steps: list[dict[str, Any]] | None
    started_at: datetime
    finished_at: datetime | None
