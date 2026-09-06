# ruff: noqa: F401, I001
"""Docker schemas — network."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.types import JsonObject


class DockerNetwork(BaseModel):
    """Network info from `docker network ls --format json`.

    Fields: ID, Name, Driver, Scope
    """

    id: str = Field(alias="ID")
    name: str = Field(alias="Name")
    driver: str = Field(alias="Driver")
    scope: str = Field(alias="Scope")

    model_config = {"populate_by_name": True}


class NetworkCreateRequest(BaseModel):
    """Request body for creating a Docker network."""

    name: str = Field(min_length=1, max_length=128)
    driver: str = Field(default="bridge", max_length=64)
    subnet: str | None = Field(default=None, max_length=64)
    gateway: str | None = Field(default=None, max_length=64)


class NetworkInspectContainer(BaseModel):
    """A container connected to a network (from network inspect)."""

    name: str
    ipv4_address: str = ""
    ipv6_address: str = ""


class NetworkInspectResponse(BaseModel):
    """Response from ``docker network inspect``."""

    id: str
    name: str
    driver: str
    scope: str
    subnet: str = ""
    gateway: str = ""
    containers: list[NetworkInspectContainer] = Field(default_factory=list)


class NetworkConnectRequest(BaseModel):
    """Request body for connecting a container to a network."""

    container_id: str = Field(min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, max_length=64)


class NetworkDisconnectRequest(BaseModel):
    """Request body for disconnecting a container from a network."""

    container_id: str = Field(min_length=1, max_length=255)
    force: bool = False


class NetworkRemovalsRequest(BaseModel):
    """Bulk network removals."""

    network_ids: list[str] = Field(min_length=1, max_length=100)


class NetworkBulkResult(BaseModel):
    """Result of a bulk network action."""

    network_id: str
    status: Literal["success", "error"]
    error: str = ""
