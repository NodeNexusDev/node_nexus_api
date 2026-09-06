# ruff: noqa: F401, I001
"""Node schemas — metrics."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.docker_validation import validate_docker_host
from app.core.types import ConnectionType, JsonObject, NodeStatus
from app.schemas.common import CursorPage, PaginatedResponse


class CpuMetrics(BaseModel):
    """CPU metrics from a node."""

    usage_percent: float = Field(ge=0, le=100)
    cores: int = Field(ge=1)


class MemoryMetrics(BaseModel):
    """Memory metrics from a node."""

    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class DiskMetrics(BaseModel):
    """Disk metrics from a node."""

    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class LoadAverage(BaseModel):
    """System load average over 1, 5, and 15 minutes."""

    one_min: float = Field(ge=0)
    five_min: float = Field(ge=0)
    fifteen_min: float = Field(ge=0)


class NodeMetrics(BaseModel):
    """System metrics from a node."""

    cpu: CpuMetrics
    memory: MemoryMetrics
    disk: DiskMetrics
    load_average: LoadAverage
    uptime_since: str


class NodeValidateRequest(BaseModel):
    """Request to validate SSH credentials without saving a node."""

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    connection_type: ConnectionType = "ssh"
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    ssh_key: str | None = Field(default=None, repr=False)
    passphrase: str | None = Field(default=None, repr=False)


class NodeValidateResponse(BaseModel):
    """Result of credential validation."""

    status: NodeStatus
    message: str


# --- Node status history ---
