from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MetricsQueryDTO:
    date_from: datetime | None = None
    date_to: datetime | None = None
    group_by: str = "day"


@dataclass(frozen=True, slots=True)
class MetricsBucketDTO:
    period: str
    total: int
    successful: int
    failed: int
    avg_duration_ms: float | None


@dataclass(frozen=True, slots=True)
class DashboardMetricsDTO:
    command_metrics: tuple[MetricsBucketDTO, ...]
    script_metrics: tuple[MetricsBucketDTO, ...]
