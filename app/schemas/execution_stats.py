from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatsResponse(BaseModel):
    """Aggregated execution statistics."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    successful: int
    failed: int
    cancelled: int = 0
    success_rate: float = Field(
        ge=0,
        le=1,
        description="Доля успешных 0..1 (0.8=80%), cancelled excluded",
    )
    avg_duration_ms: float | None = None
    min_duration_ms: float | None = None
    max_duration_ms: float | None = None
    last_executed_at: datetime | None = None


class StatsBucket(BaseModel):
    """Single time bucket for stats grouping."""

    period: str
    total: int
    successful: int
    failed: int
    cancelled: int
    avg_duration_ms: float | None = None


class StatsBucketsResponse(BaseModel):
    """Buckets response when group_by is present."""

    buckets: list[StatsBucket]
