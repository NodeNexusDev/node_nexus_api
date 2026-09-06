# ruff: noqa: F401, I001
"""Node schemas — node."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.docker_validation import validate_docker_host
from app.core.types import ConnectionType, JsonObject, NodeStatus
from app.schemas.common import CursorPage, PaginatedResponse


class NodeCreate(BaseModel):
    """Schema for creating a node."""

    name: str = Field(min_length=1, max_length=255)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    connection_type: ConnectionType = "ssh"
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    ssh_key: str | None = Field(default=None, repr=False)
    passphrase: str | None = Field(default=None, repr=False)
    docker_host: str | None = None
    has_docker: bool = Field(
        default=False, description="Logical docker capability toggle"
    )
    tags: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def check_docker_fields(self) -> Self:
        if self.docker_host is not None and not self.has_docker:
            raise ValueError("docker_host requires has_docker=true")
        if self.docker_host is not None:
            try:
                validate_docker_host(self.docker_host)
            except Exception as exc:
                raise ValueError(str(exc)) from exc
        return self


class NodeUpdate(BaseModel):
    """Schema for updating a node."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    connection_type: ConnectionType | None = None
    status: NodeStatus | None = None
    username: str | None = None
    password: str | None = Field(default=None, repr=False)
    ssh_key: str | None = Field(default=None, repr=False)
    passphrase: str | None = Field(default=None, repr=False)
    docker_host: str | None = None
    has_docker: bool | None = Field(
        default=None, description="Logical docker capability toggle"
    )
    tags: list[str] | None = None
    description: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def check_docker_fields_update(self) -> Self:
        if self.docker_host is not None and self.has_docker is False:
            raise ValueError("docker_host requires has_docker=true")
        if self.docker_host is not None:
            try:
                validate_docker_host(self.docker_host)
            except Exception as exc:
                raise ValueError(str(exc)) from exc
        return self


class NodeResponse(BaseModel):
    """Schema for node response. Never includes secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    host: str
    port: int
    connection_type: ConnectionType
    status: NodeStatus
    username: str | None
    docker_host: str | None
    has_docker: bool
    tags: list[str]
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class NodeOffsetListResponse(PaginatedResponse[NodeResponse]):
    """Offset-based paginated list of nodes."""


class NodeCursorListResponse(CursorPage[NodeResponse]):
    """Cursor-based paginated list of nodes."""


class NodeStatusHistoryItem(BaseModel):
    """Single status change record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: uuid.UUID | None = None
    old_status: str | None = None
    new_status: str
    source: str
    changed_at: datetime


class NodeStatusHistoryResponse(PaginatedResponse[NodeStatusHistoryItem]):
    """Paginated status history for a node."""

    pass


# --- Bulk node operations ---
