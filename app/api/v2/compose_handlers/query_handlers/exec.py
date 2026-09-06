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


@router.post("/projects/{project_name}/executions", response_model=ComposeExecResponse)
@inject
async def compose_exec(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeExecRequest,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeExecResponse:
    """Execute a command in a compose service via ``compose exec``."""
    audit.info(
        "api.v2.compose.projects.executions",
        node_id=str(node_id),
        project_name=project_name,
        service=data.service,
    )
    _validate_project_name(project_name)
    try:
        stdout, stderr, exit_code = await service.exec(
            node_id,
            project_name,
            service=data.service,
            command=data.command,
            timeout=data.timeout,
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeExecResponse(stdout=stdout, stderr=stderr, exit_code=exit_code)


@router.post("/projects/{project_name}/runs", response_model=ComposeRunResponse)
@inject
async def compose_run(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeRunRequest,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeRunResponse:
    """Run a one-off command via ``compose run``."""
    audit.info(
        "api.v2.compose.projects.runs",
        node_id=str(node_id),
        project_name=project_name,
        service=data.service,
    )
    _validate_project_name(project_name)
    try:
        out = await service.run(
            node_id,
            project_name,
            service=data.service,
            command=data.command,
            detached=data.detached,
            timeout=data.timeout,
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeRunResponse(output=out)
