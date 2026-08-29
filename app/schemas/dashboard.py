"""Dashboard schemas for API."""

from datetime import datetime

from pydantic import BaseModel


class NodeStats(BaseModel):
    """Aggregated node statistics."""

    total: int
    active: int
    unreachable: int


class DashboardDockerStats(BaseModel):
    """Aggregated Docker container statistics."""

    total: int
    running: int
    stopped: int


class EntityStats(BaseModel):
    """Generic entity count."""

    total: int


class RecentActivity(BaseModel):
    """One recent audit log entry."""

    id: str
    action: str
    node_id: str | None = None
    user: str | None = None
    details: str | None = None
    created_at: datetime


class DashboardResponse(BaseModel):
    """Full dashboard overview response."""

    nodes: NodeStats
    docker: DashboardDockerStats
    scripts: EntityStats
    commands: EntityStats
    recent_activity: list[RecentActivity]


class MetricsBucket(BaseModel):
    """One time-series bucket."""

    period: str
    total: int
    successful: int
    failed: int
    cancelled: int = 0
    avg_duration_ms: float | None = None


class DashboardMetricsResponse(BaseModel):
    """Time-series execution metrics for charts."""

    command_metrics: list[MetricsBucket]
    script_metrics: list[MetricsBucket]
