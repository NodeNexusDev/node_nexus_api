from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExecutionStatsResponse(BaseModel):
    """Aggregated execution statistics."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    successful: int
    failed: int
    success_rate: float
    avg_duration_ms: float | None = None
    min_duration_ms: float | None = None
    max_duration_ms: float | None = None
    last_executed_at: datetime | None = None
