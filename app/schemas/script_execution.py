"""Script execution schemas for API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.application.dto.script_execution import ScriptExecutionStatus
from app.core.types import JsonObject
from app.schemas.script import ScriptStepResult


class ScriptExecutionResponse(BaseModel):
    """Schema for a single script execution record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    script_id: uuid.UUID
    node_id: uuid.UUID | None
    params: JsonObject | None
    status: ScriptExecutionStatus
    steps: list[ScriptStepResult] | None
    started_at: datetime
    finished_at: datetime | None
