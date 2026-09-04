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
router = APIRouter(route_class=DishkaRoute)

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
    "/projects/{project_name}/starts",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_starts(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Start services via ``compose start``."""
    audit.info(
        "api.v2.compose.projects.starts",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.verb_bulk(node_id, project_name, "start", data.services)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = _bulk_to_response(bulk)
    if result.failed > 0 and result.succeeded > 0:
        response.status_code = 207
    return result


@router.post(
    "/projects/{project_name}/stops",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_stops(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    timeout: int = Query(10, ge=1, le=600),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Stop services via ``compose stop``."""
    audit.info(
        "api.v2.compose.projects.stops", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    extra = f" -t {timeout}" if timeout else ""
    try:
        bulk = await service.verb_bulk(
            node_id, project_name, "stop", data.services, extra=extra
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = _bulk_to_response(bulk)
    if result.failed > 0 and result.succeeded > 0:
        response.status_code = 207
    return result


@router.post(
    "/projects/{project_name}/restarts",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_restarts(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    timeout: int = Query(10, ge=1, le=600),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Restart services via ``compose restart``."""
    audit.info(
        "api.v2.compose.projects.restarts",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    extra = f" -t {timeout}" if timeout else ""
    try:
        bulk = await service.verb_bulk(
            node_id, project_name, "restart", data.services, extra=extra
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = _bulk_to_response(bulk)
    if result.failed > 0 and result.succeeded > 0:
        response.status_code = 207
    return result


