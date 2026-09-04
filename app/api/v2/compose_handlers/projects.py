# ruff: noqa: F401, I001
"""Compose project HTTP adapter v2 with cursor pagination and runtime."""

from __future__ import annotations

import re
import uuid
from typing import Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security, status

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.pagination import decode_offset, encode_offset, paginate_offset
from app.application.dto.compose import ComposeCreateDTO, ComposeUpdateDTO
from app.application.services.compose_service import ComposeService
from app.core.exceptions import (
    ComposeProjectAlreadyExistsError,
    ComposeProjectNotFoundError,
)
from app.schemas.common import BulkResult, CursorPage
from app.schemas.compose import (
    ComposeActionResponse,
    ComposeConfigResponse,
    ComposeCreate,
    ComposeDownRequest,
    ComposeExecRequest,
    ComposeExecResponse,
    ComposeImagesResponse,
    ComposeKillRequest,
    ComposeLogsResponse,
    ComposePortResponse,
    ComposePsResponse,
    ComposeResponse,
    ComposeRunRequest,
    ComposeRunResponse,
    ComposeServiceBulkResult,
    ComposeServicesRequest,
    ComposeTopResponse,
    ComposeUpdate,
    ComposeUpRequest,
    ComposeVersionResponse,
)

audit = structlog.get_logger("audit")

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816
_paginate_offset = paginate_offset  # noqa: N816
router = APIRouter(tags=["docker-compose"], route_class=DishkaRoute)

_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _validate_project_name(name: str) -> str:
    """Validate compose project_name format."""
    if not name or not _PROJECT_NAME_RE.fullmatch(name) or len(name) > 100:
        raise HTTPException(status_code=422, detail=f"Invalid project_name: {name!r}")
    return name


def _to_response(dto: object) -> ComposeResponse:
    """Map DTO to response schema."""
    # dto is ComposeViewDTO
    from app.application.dto.compose import ComposeViewDTO as _Dto  # noqa: N814

    if not isinstance(dto, _Dto):
        raise TypeError(f"Expected ComposeViewDTO, got {type(dto).__name__}")
    return ComposeResponse(
        id=dto.id,
        node_id=dto.node_id,
        project_name=dto.project_name,
        compose=dto.compose,
        env=dto.env,
        template_pack_id=dto.template_pack_id,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
    )


def _bulk_to_response(
    bulk: object,
) -> BulkResult[ComposeServiceBulkResult]:
    """Map ComposeBulkResultDTO to BulkResult schema."""
    from typing import cast

    from app.application.dto.compose import (
        ComposeBulkResultDTO as _BulkDto,  # noqa: N814
    )

    if not isinstance(bulk, _BulkDto):
        raise TypeError(f"Expected ComposeBulkResultDTO, got {type(bulk).__name__}")
    results = [
        ComposeServiceBulkResult(
            service=r.service,
            status=cast(Literal["success", "error"], r.status),
            error=r.error,
            output=r.output,
        )
        for r in bulk.results
    ]
    return BulkResult[ComposeServiceBulkResult](
        total=bulk.total, succeeded=bulk.succeeded, failed=bulk.failed, results=results
    )


# ---------------------------------------------------------------------------
# Pure DB — CRUD (projects)
# ---------------------------------------------------------------------------


@router.post(
    "/projects", response_model=ComposeResponse, status_code=status.HTTP_201_CREATED
)
@inject
async def create_project(
    node_id: uuid.UUID,
    data: ComposeCreate,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeResponse:
    """Create a compose project (pure DB)."""
    audit.info(
        "api.v2.compose.projects.create",
        node_id=str(node_id),
        project_name=data.project_name,
    )
    _validate_project_name(data.project_name)
    dto = ComposeCreateDTO(
        node_id=node_id,
        project_name=data.project_name,
        compose=data.compose,
        env=tuple(data.env.items()) if data.env else (),
        template_pack_id=data.template_pack_id,
    )
    try:
        created = await service.create_project(dto)
    except ComposeProjectAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Project already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(created)


@router.get("/projects", response_model=CursorPage[ComposeResponse])
@inject
async def list_projects(
    node_id: uuid.UUID,
    service: FromDishka[ComposeService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[ComposeResponse]:
    """List compose projects with cursor pagination."""
    audit.info("api.v2.compose.projects.list", node_id=str(node_id), limit=limit)
    all_items = await service.list_all_projects(node_id)
    mapped = [_to_response(m) for m in all_items]
    paged, next_cursor, has_more = paginate_offset(mapped, cursor, limit)
    return CursorPage[ComposeResponse](
        items=paged, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.get("/projects/{project_name}", response_model=ComposeResponse)
@inject
async def get_project(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(get_current_principal),
) -> ComposeResponse:
    """Get a compose project by name."""
    audit.info(
        "api.v2.compose.projects.get", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        project = await service.get_project(node_id, project_name)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(project)


@router.patch("/projects/{project_name}", response_model=ComposeResponse)
@inject
async def update_project(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeUpdate,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeResponse:
    """Update a compose project (partial)."""
    audit.info(
        "api.v2.compose.projects.update",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    dto = ComposeUpdateDTO(
        compose=data.compose,
        env=tuple(data.env.items()) if data.env is not None else None,
        has_env=data.env is not None,
        template_pack_id=data.template_pack_id,
        has_template_pack_id="template_pack_id" in data.model_fields_set,
    )
    try:
        updated = await service.update_project(node_id, project_name, dto)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_response(updated)


@router.delete("/projects/{project_name}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_project(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a compose project (pure DB)."""
    audit.info(
        "api.v2.compose.projects.delete",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        await service.delete_project(node_id, project_name)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Runtime — ups / downs
# ---------------------------------------------------------------------------
