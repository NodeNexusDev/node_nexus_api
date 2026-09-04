# ruff: noqa: F401, I001
"""Docker schemas — volume."""

import uuid
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core.types import JsonObject


class DockerVolume(BaseModel):
    """Volume info from `docker volume ls --format json`.

    Fields: Driver, Name
    """

    driver: str = Field(alias="Driver")
    name: str = Field(alias="Name")

    model_config = {"populate_by_name": True}


class VolumeCreateRequest(BaseModel):
    """Request body for creating a Docker volume."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    driver: str = Field(default="local", max_length=64)


class VolumeInspectResponse(BaseModel):
    """Response from ``docker volume inspect``."""

    name: str
    driver: str
    mountpoint: str
    labels: dict[str, str] = Field(default_factory=dict)


class VolumeRemovalsRequest(BaseModel):
    """Bulk volume removals."""

    volume_names: list[str] = Field(min_length=1, max_length=100)


class VolumeBulkResult(BaseModel):
    """Result of a bulk volume action."""

    volume_name: str
    status: Literal["success", "error"]
    error: str = ""
