"""Compose project HTTP adapter v2 with cursor pagination and runtime."""

from __future__ import annotations

import base64
import json
import re
import uuid
from typing import Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security, status

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
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
router = APIRouter(
    prefix="/nodes/{node_id}/docker/compose",
    tags=["docker-compose"],
    route_class=DishkaRoute,
)

_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


# ---------------------------------------------------------------------------
# Cursor helpers (offset-based)
# ---------------------------------------------------------------------------


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


def _paginate_offset[T](
    items: list[T], cursor: str | None, limit: int
) -> tuple[list[T], str | None, bool]:
    """Slice items by offset cursor."""
    offset = 0
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    sliced = items[offset : offset + limit]
    has_more = (offset + len(sliced)) < len(items)
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return sliced, next_cursor, has_more


def _validate_project_name(name: str) -> str:
    """Validate compose project_name format."""
    if not name or not _PROJECT_NAME_RE.fullmatch(name) or len(name) > 100:
        raise HTTPException(status_code=422, detail=f"Invalid project_name: {name!r}")
    return name


def _to_response(dto: object) -> ComposeResponse:
    """Map DTO to response schema."""
    # dto is ComposeViewDTO
    from app.application.dto.compose import ComposeViewDTO as _Dto  # noqa: N814

    assert isinstance(dto, _Dto)
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

    assert isinstance(bulk, _BulkDto)
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
    paged, next_cursor, has_more = _paginate_offset(mapped, cursor, limit)
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


@router.post(
    "/projects/{project_name}/ups",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_up(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeUpRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Deploy a compose project via ``compose up -d`` with 207 handling."""
    audit.info(
        "api.v2.compose.projects.ups", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.up(
            node_id,
            project_name,
            pull=data.pull,
            build=data.build,
            services=data.services,
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
    "/projects/{project_name}/downs",
    response_model=ComposeActionResponse,
)
@inject
async def compose_down(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeDownRequest,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeActionResponse:
    """Tear down a compose project via ``compose down``."""
    audit.info(
        "api.v2.compose.projects.downs", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        out = await service.down(
            node_id,
            project_name,
            volumes=data.volumes,
            remove_orphans=data.remove_orphans,
            timeout=data.timeout,
            images=data.images,
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeActionResponse(status="down", output=out)


# ---------------------------------------------------------------------------
# Runtime — verb bulk with 207
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


@router.post(
    "/projects/{project_name}/pauses",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_pauses(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Pause services via ``compose pause``."""
    audit.info(
        "api.v2.compose.projects.pauses",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.verb_bulk(node_id, project_name, "pause", data.services)
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
    "/projects/{project_name}/unpauses",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_unpauses(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Unpause services via ``compose unpause``."""
    audit.info(
        "api.v2.compose.projects.unpauses",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.verb_bulk(node_id, project_name, "unpause", data.services)
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
    "/projects/{project_name}/kills",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_kills(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeKillRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Kill services via ``compose kill``."""
    audit.info(
        "api.v2.compose.projects.kills", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    extra = f" -s {data.signal}" if data.signal else ""
    try:
        bulk = await service.verb_bulk(
            node_id, project_name, "kill", data.services, extra=extra
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
    "/projects/{project_name}/creates",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_creates(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Create services via ``compose create``."""
    audit.info(
        "api.v2.compose.projects.creates",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.verb_bulk(node_id, project_name, "create", data.services)
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
    "/projects/{project_name}/rms",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_rms(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    volumes: bool = Query(False),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Remove services via ``compose rm``."""
    audit.info(
        "api.v2.compose.projects.rms", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    extra = " -f"
    if volumes:
        extra += " -v"
    try:
        bulk = await service.verb_bulk(
            node_id, project_name, "rm", data.services, extra=extra
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
    "/projects/{project_name}/pulls",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_pulls(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Pull images via ``compose pull``."""
    audit.info(
        "api.v2.compose.projects.pulls", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.verb_bulk(node_id, project_name, "pull", data.services)
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
    "/projects/{project_name}/pushs",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_pushs(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Push images via ``compose push``."""
    audit.info(
        "api.v2.compose.projects.pushs", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        bulk = await service.verb_bulk(node_id, project_name, "push", data.services)
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
    "/projects/{project_name}/builds",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_builds(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    service: FromDishka[ComposeService],
    response: Response,
    no_cache: bool = Query(False),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Build images via ``compose build``."""
    audit.info(
        "api.v2.compose.projects.builds",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    extra = " --no-cache" if no_cache else ""
    try:
        bulk = await service.verb_bulk(
            node_id, project_name, "build", data.services, extra=extra
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


# ---------------------------------------------------------------------------
# Runtime — GET ps, logs, config, images, top, port, version + POST exec/run
# ---------------------------------------------------------------------------


@router.get("/projects/{project_name}/ps", response_model=ComposePsResponse)
@inject
async def compose_ps(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    all: bool = Query(False),  # noqa: A002
    _principal: Principal = Security(get_current_principal),
) -> ComposePsResponse:
    """List containers for a compose project via ``compose ps``."""
    audit.info(
        "api.v2.compose.projects.ps", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        dto = await service.ps(node_id, project_name, all=all)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposePsResponse(output=dto.output, containers=list(dto.containers))


@router.get("/projects/{project_name}/logs", response_model=ComposeLogsResponse)
@inject
async def compose_logs(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    tail: int = Query(100, ge=1, le=10000),
    since: str | None = Query(None),
    services: str | None = Query(None, description="Optional service name"),
    _principal: Principal = Security(get_current_principal),
) -> ComposeLogsResponse:
    """Get logs for a compose project via ``compose logs``."""
    audit.info(
        "api.v2.compose.projects.logs", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        out = await service.logs(
            node_id, project_name, tail=tail, since=since, services=services
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeLogsResponse(output=out, logs=out)


@router.get("/projects/{project_name}/config", response_model=ComposeConfigResponse)
@inject
async def compose_config(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(get_current_principal),
) -> ComposeConfigResponse:
    """Return resolved compose config via ``compose config``."""
    audit.info(
        "api.v2.compose.projects.config",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        out = await service.config(node_id, project_name)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeConfigResponse(config=out, output=out)


@router.get("/projects/{project_name}/images", response_model=ComposeImagesResponse)
@inject
async def compose_images(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(get_current_principal),
) -> ComposeImagesResponse:
    """List images for a compose project via ``compose images``."""
    audit.info(
        "api.v2.compose.projects.images",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        images, out = await service.images(node_id, project_name)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeImagesResponse(images=images, output=out)


@router.get("/projects/{project_name}/top", response_model=ComposeTopResponse)
@inject
async def compose_top(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    service_name: str | None = Query(None, alias="service", max_length=100),
    _principal: Principal = Security(get_current_principal),
) -> ComposeTopResponse:
    """Return processes via ``compose top``."""
    audit.info(
        "api.v2.compose.projects.top", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        titles, processes, out = await service.top(
            node_id, project_name, service=service_name
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeTopResponse(titles=titles, processes=processes, output=out)


@router.get("/projects/{project_name}/port", response_model=ComposePortResponse)
@inject
async def compose_port(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    service_name: str = Query(..., alias="service", min_length=1, max_length=100),
    private_port: str = Query(..., min_length=1, max_length=20),
    _principal: Principal = Security(get_current_principal),
) -> ComposePortResponse:
    """Return port bindings via ``compose port``."""
    audit.info(
        "api.v2.compose.projects.port", node_id=str(node_id), project_name=project_name
    )
    _validate_project_name(project_name)
    try:
        out = await service.port(
            node_id, project_name, service=service_name, private_port=private_port
        )
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposePortResponse(output=out, bindings=out)


@router.get("/projects/{project_name}/version", response_model=ComposeVersionResponse)
@inject
async def compose_version(
    node_id: uuid.UUID,
    project_name: str,
    service: FromDishka[ComposeService],
    _principal: Principal = Security(get_current_principal),
) -> ComposeVersionResponse:
    """Return compose version via ``compose version``."""
    audit.info(
        "api.v2.compose.projects.version",
        node_id=str(node_id),
        project_name=project_name,
    )
    _validate_project_name(project_name)
    try:
        ver, out = await service.version(node_id, project_name)
    except ComposeProjectNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Compose project not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ComposeVersionResponse(version=ver, output=out)


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
