"""System metrics application DTOs."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CpuMetricsDTO:
    """CPU utilization snapshot."""

    usage_percent: float
    cores: int


@dataclass(frozen=True, slots=True)
class UsageMetricsDTO:
    """Capacity and utilization snapshot."""

    total_bytes: int
    used_bytes: int
    percent: float


@dataclass(frozen=True, slots=True)
class NodeMetricsDTO:
    """Transport-independent system metrics for one node."""

    cpu: CpuMetricsDTO
    memory: UsageMetricsDTO
    disk: UsageMetricsDTO
    uptime_since: str
