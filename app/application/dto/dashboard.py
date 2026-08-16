"""Immutable DTOs for the dashboard overview."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DashboardNodeStatsDTO:
    """Aggregated node statistics."""

    total: int
    active: int
    unreachable: int


@dataclass(frozen=True, slots=True)
class DashboardDockerStatsDTO:
    """Aggregated Docker container statistics."""

    total: int
    running: int
    stopped: int


@dataclass(frozen=True, slots=True)
class DashboardEntityStatsDTO:
    """Generic entity count."""

    total: int


@dataclass(frozen=True, slots=True)
class DashboardRecentActivityDTO:
    """One recent audit log entry."""

    id: str
    action: str
    node_id: str | None
    user: str | None
    details: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DashboardDTO:
    """Full dashboard overview."""

    nodes: DashboardNodeStatsDTO
    docker: DashboardDockerStatsDTO
    scripts: DashboardEntityStatsDTO
    commands: DashboardEntityStatsDTO
    recent_activity: tuple[DashboardRecentActivityDTO, ...]
