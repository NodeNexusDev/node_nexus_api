"""Compose project HTTP adapter v2 with cursor pagination and runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import shlex
import uuid
from typing import Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.dto.compose import ComposeCreateDTO, ComposeUpdateDTO
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.error_mapper import raise_for_docker_error
from app.models.compose_project import ComposeProjectModel
from app.schemas.common import BulkResult, CursorPage
from app.schemas.compose import ComposeCreate, ComposeResponse, ComposeUpdate

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


def _compose_file_path(project_name: str) -> str:
    """Safe temp compose file path for a project."""
    safe = "".join(c if c.isalnum() else "_" for c in project_name)
    return f"/tmp/nn-compose-{safe}.yml"


def _env_prefix(env: dict[str, str] | None) -> str:
    """Build env var prefix for docker compose commands."""
    if not env:
        return ""
    parts = [f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items()]
    return " ".join(parts) + " "


async def _get_project(
    session: AsyncSession, node_id: uuid.UUID, project_name: str
) -> ComposeProjectModel:
    """Fetch a compose project or raise 404."""
    validated = _validate_project_name(project_name)
    result = await session.execute(
        select(ComposeProjectModel).where(
            ComposeProjectModel.node_id == node_id,
            ComposeProjectModel.project_name == validated,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Compose project not found")
    return project


async def _run_compose(
    runner: DockerCommandRunner,
    node_id: uuid.UUID,
    project: ComposeProjectModel,
    compose_args: str,
    timeout: int = 60,
) -> str:
    """Write compose file and run ``docker compose``."""
    node = await runner.get_target(node_id)
    file_path = _compose_file_path(project.project_name)
    env_str = _env_prefix(project.env)  # type: ignore[arg-type]
    quoted = shlex.quote(project.compose)
    write_cmd = f"printf %s {quoted} > {shlex.quote(file_path)}"
    docker_args = (
        f"compose -p {shlex.quote(project.project_name)} "
        f"-f {shlex.quote(file_path)} {compose_args}"
    )
    docker_cmd = runner.build_command(node, docker_args)
    full = f"{write_cmd} && {env_str}{docker_cmd}"
    stdout, stderr, exit_code = await runner.execute(node, full, timeout=timeout)
    raise_for_docker_error(stderr, exit_code)
    return stdout.strip()


# ---------------------------------------------------------------------------
# Local schemas for compose runtime (v2)
# ---------------------------------------------------------------------------


class ComposeUpRequest(BaseModel):
    """Request for ``compose up``."""

    pull: bool = Field(default=False, description="Pull images before up")
    build: bool = Field(default=False, description="Build images before up")
    services: list[str] | None = Field(
        default=None, min_length=1, max_length=100, description="Target services"
    )


class ComposeDownRequest(BaseModel):
    """Request for ``compose down``."""

    volumes: bool = Field(default=False, description="Remove volumes")
    remove_orphans: bool = Field(default=False, description="Remove orphans")
    timeout: int | None = Field(default=None, ge=1, le=600)
    images: str | None = Field(default=None, max_length=64, description="all|local")


class ComposeServicesRequest(BaseModel):
    """Services selection for verb bulk."""

    services: list[str] | None = Field(
        default=None, min_length=1, max_length=100, description="Target services"
    )


class ComposeKillRequest(BaseModel):
    """Kill request with signal."""

    signal: str = Field(default="SIGTERM", min_length=1, max_length=20)
    services: list[str] | None = Field(default=None, min_length=1, max_length=100)


class ComposeExecRequest(BaseModel):
    """Compose exec request."""

    service: str = Field(min_length=1, max_length=100)
    command: str = Field(min_length=1, max_length=4096)
    timeout: int = Field(default=30, ge=1, le=600)


class ComposeRunRequest(BaseModel):
    """Compose run request."""

    service: str = Field(min_length=1, max_length=100)
    command: str | None = Field(default=None, min_length=1, max_length=4096)
    detached: bool = Field(default=False)
    timeout: int = Field(default=60, ge=1, le=600)


class ComposeServiceBulkResult(BaseModel):
    """Bulk result for per-service compose verb."""

    service: str
    status: Literal["success", "error"]
    error: str = ""
    output: str = ""


class ComposePsResponse(BaseModel):
    """Response for ``compose ps``."""

    output: str
    containers: list[dict[str, str]] = Field(default_factory=list)


class ComposeLogsResponse(BaseModel):
    """Response for ``compose logs``."""

    output: str
    logs: str = ""


class ComposeConfigResponse(BaseModel):
    """Response for ``compose config``."""

    config: str
    output: str = ""


class ComposeImagesResponse(BaseModel):
    """Response for ``compose images``."""

    images: list[str] = Field(default_factory=list)
    output: str = ""


class ComposeTopResponse(BaseModel):
    """Response for ``compose top``."""

    titles: list[str] = Field(default_factory=list)
    processes: list[list[str]] = Field(default_factory=list)
    output: str = ""


class ComposePortResponse(BaseModel):
    """Response for ``compose port``."""

    output: str
    bindings: str = ""


class ComposeExecResponse(BaseModel):
    """Response for ``compose exec``."""

    stdout: str
    stderr: str
    exit_code: int


class ComposeRunResponse(BaseModel):
    """Response for ``compose run``."""

    output: str


class ComposeVersionResponse(BaseModel):
    """Response for ``compose version``."""

    version: str
    output: str = ""


class ComposeActionResponse(BaseModel):
    """Generic action response."""

    status: str
    output: str = ""


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
    session: FromDishka[AsyncSession],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeResponse:
    """Create a compose project (pure DB)."""
    audit.info(
        "api.v2.compose.projects.create",
        node_id=str(node_id),
        project_name=data.project_name,
    )
    _validate_project_name(data.project_name)
    # map schema -> DTO (application layer)
    dto = ComposeCreateDTO(
        node_id=node_id,
        project_name=data.project_name,
        compose=data.compose,
        env=tuple(data.env.items()) if data.env else (),
        template_pack_id=data.template_pack_id,
    )
    # check duplicates
    existing = await session.execute(
        select(ComposeProjectModel).where(
            ComposeProjectModel.node_id == node_id,
            ComposeProjectModel.project_name == dto.project_name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Project already exists")
    model = ComposeProjectModel(
        id=uuid.uuid4(),
        node_id=dto.node_id,
        project_name=dto.project_name,
        compose=dto.compose,
        env=dict(dto.env) if dto.env else None,
        template_pack_id=dto.template_pack_id,
    )
    session.add(model)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Project already exists") from exc
    return ComposeResponse.model_validate(model, from_attributes=True)


@router.get("/projects", response_model=CursorPage[ComposeResponse])
@inject
async def list_projects(
    node_id: uuid.UUID,
    session: FromDishka[AsyncSession],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[ComposeResponse]:
    """List compose projects with cursor pagination."""
    audit.info("api.v2.compose.projects.list", node_id=str(node_id), limit=limit)
    result = await session.execute(
        select(ComposeProjectModel)
        .where(ComposeProjectModel.node_id == node_id)
        .order_by(ComposeProjectModel.created_at.desc(), ComposeProjectModel.id.desc())
    )
    all_items = list(result.scalars().all())
    paged, next_cursor, has_more = _paginate_offset(
        [ComposeResponse.model_validate(m, from_attributes=True) for m in all_items],
        cursor,
        limit,
    )
    return CursorPage[ComposeResponse](
        items=paged, next_cursor=next_cursor, has_more=has_more, limit=limit
    )


@router.get("/projects/{project_name}", response_model=ComposeResponse)
@inject
async def get_project(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    _principal: Principal = Security(get_current_principal),
) -> ComposeResponse:
    """Get a compose project by name."""
    audit.info(
        "api.v2.compose.projects.get", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    return ComposeResponse.model_validate(project, from_attributes=True)


@router.patch("/projects/{project_name}", response_model=ComposeResponse)
@inject
async def update_project(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeUpdate,
    session: FromDishka[AsyncSession],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeResponse:
    """Update a compose project (partial)."""
    audit.info(
        "api.v2.compose.projects.update",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    # map schema -> DTO for update
    dto = ComposeUpdateDTO(
        compose=data.compose,
        env=tuple(data.env.items()) if data.env is not None else None,
        has_env=data.env is not None,
        template_pack_id=data.template_pack_id,
        has_template_pack_id="template_pack_id" in data.model_fields_set,
    )
    if dto.compose is not None:
        project.compose = dto.compose  # type: ignore[assignment]
    if dto.has_env and dto.env is not None:
        project.env = dict(dto.env)  # type: ignore[assignment]
    elif dto.has_env and dto.env is None:
        project.env = None  # type: ignore[assignment]
    if dto.has_template_pack_id:
        project.template_pack_id = dto.template_pack_id  # type: ignore[assignment]
    await session.flush()
    return ComposeResponse.model_validate(project, from_attributes=True)


@router.delete("/projects/{project_name}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_project(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a compose project (pure DB)."""
    audit.info(
        "api.v2.compose.projects.delete",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    await session.delete(project)
    await session.flush()


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
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Deploy a compose project via ``compose up -d`` with 207 handling."""
    audit.info(
        "api.v2.compose.projects.ups", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    extra = " up -d"
    if data.pull:
        extra += " --pull always"
    if data.build:
        extra += " --build"
    services = data.services

    async def _one(svc: str) -> ComposeServiceBulkResult:
        try:
            out = await _run_compose(
                runner, node_id, project, f"{extra} {shlex.quote(svc)}"
            )
            return ComposeServiceBulkResult(service=svc, status="success", output=out)
        except Exception as exc:  # noqa: BLE001
            return ComposeServiceBulkResult(service=svc, status="error", error=str(exc))

    if not services:
        try:
            out = await _run_compose(runner, node_id, project, extra)
            result = ComposeServiceBulkResult(
                service=project_name, status="success", output=out
            )
            return BulkResult[ComposeServiceBulkResult](
                total=1, succeeded=1, failed=0, results=[result]
            )
        except Exception as exc:  # noqa: BLE001
            result = ComposeServiceBulkResult(
                service=project_name, status="error", error=str(exc)
            )
            return BulkResult[ComposeServiceBulkResult](
                total=1, succeeded=0, failed=1, results=[result]
            )

    results = await asyncio.gather(*(_one(s) for s in services))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=list(results)
    )


@router.post(
    "/projects/{project_name}/downs",
    response_model=ComposeActionResponse,
)
@inject
async def compose_down(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeDownRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeActionResponse:
    """Tear down a compose project via ``compose down``."""
    audit.info(
        "api.v2.compose.projects.downs", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    extra = " down"
    if data.volumes:
        extra += " -v"
    if data.remove_orphans:
        extra += " --remove-orphans"
    if data.images:
        extra += f" --rmi {shlex.quote(data.images)}"
    if data.timeout is not None:
        extra += f" -t {data.timeout}"
    out = await _run_compose(runner, node_id, project, extra, timeout=120)
    return ComposeActionResponse(status="down", output=out)


# ---------------------------------------------------------------------------
# Runtime — verb bulk with asyncio.gather and 207
# ---------------------------------------------------------------------------


async def _bulk_verb(
    node_id: uuid.UUID,
    project: ComposeProjectModel,
    runner: DockerCommandRunner,
    verb: str,
    services: list[str] | None,
    extra: str = "",
    timeout: int = 60,
) -> list[ComposeServiceBulkResult]:
    """Run a compose verb per service with gather."""
    if not services:
        try:
            out = await _run_compose(
                runner, node_id, project, f"{verb}{extra}", timeout=timeout
            )
            return [
                ComposeServiceBulkResult(
                    service=project.project_name, status="success", output=out
                )
            ]
        except Exception as exc:  # noqa: BLE001
            return [
                ComposeServiceBulkResult(
                    service=project.project_name, status="error", error=str(exc)
                )
            ]

    async def _one(svc: str) -> ComposeServiceBulkResult:
        try:
            out = await _run_compose(
                runner,
                node_id,
                project,
                f"{verb}{extra} {shlex.quote(svc)}",
                timeout=timeout,
            )
            return ComposeServiceBulkResult(service=svc, status="success", output=out)
        except Exception as exc:  # noqa: BLE001
            return ComposeServiceBulkResult(service=svc, status="error", error=str(exc))

    results = await asyncio.gather(*(_one(s) for s in services))
    return list(results)


@router.post(
    "/projects/{project_name}/starts",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_starts(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Start services via ``compose start``."""
    audit.info(
        "api.v2.compose.projects.starts",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    results = await _bulk_verb(node_id, project, runner, "start", data.services)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/stops",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_stops(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    timeout: int = Query(10, ge=1, le=600),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Stop services via ``compose stop``."""
    audit.info(
        "api.v2.compose.projects.stops", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    extra = f" -t {timeout}" if timeout else ""
    results = await _bulk_verb(
        node_id, project, runner, "stop", data.services, extra=extra
    )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/restarts",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_restarts(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
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
    project = await _get_project(session, node_id, project_name)
    extra = f" -t {timeout}" if timeout else ""
    results = await _bulk_verb(
        node_id, project, runner, "restart", data.services, extra=extra
    )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/pauses",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_pauses(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Pause services via ``compose pause``."""
    audit.info(
        "api.v2.compose.projects.pauses",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    results = await _bulk_verb(node_id, project, runner, "pause", data.services)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/unpauses",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_unpauses(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Unpause services via ``compose unpause``."""
    audit.info(
        "api.v2.compose.projects.unpauses",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    results = await _bulk_verb(node_id, project, runner, "unpause", data.services)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/kills",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_kills(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeKillRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Kill services via ``compose kill``."""
    audit.info(
        "api.v2.compose.projects.kills", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    extra = f" -s {shlex.quote(data.signal)}" if data.signal else ""
    results = await _bulk_verb(
        node_id, project, runner, "kill", data.services, extra=extra
    )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/creates",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_creates(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Create services via ``compose create``."""
    audit.info(
        "api.v2.compose.projects.creates",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    results = await _bulk_verb(node_id, project, runner, "create", data.services)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/rms",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_rms(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    volumes: bool = Query(False),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Remove services via ``compose rm``."""
    audit.info(
        "api.v2.compose.projects.rms", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    extra = " -f"
    if volumes:
        extra += " -v"
    results = await _bulk_verb(
        node_id, project, runner, "rm", data.services, extra=extra
    )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/pulls",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_pulls(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Pull images via ``compose pull``."""
    audit.info(
        "api.v2.compose.projects.pulls", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    results = await _bulk_verb(node_id, project, runner, "pull", data.services)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/pushs",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_pushs(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[ComposeServiceBulkResult]:
    """Push images via ``compose push``."""
    audit.info(
        "api.v2.compose.projects.pushs", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    results = await _bulk_verb(node_id, project, runner, "push", data.services)
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


@router.post(
    "/projects/{project_name}/builds",
    response_model=BulkResult[ComposeServiceBulkResult],
)
@inject
async def compose_builds(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeServicesRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
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
    project = await _get_project(session, node_id, project_name)
    extra = " --no-cache" if no_cache else ""
    results = await _bulk_verb(
        node_id, project, runner, "build", data.services, extra=extra
    )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[ComposeServiceBulkResult](
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )


# ---------------------------------------------------------------------------
# Runtime — GET ps, logs, config, images, top, port, version + POST exec/run
# ---------------------------------------------------------------------------


@router.get("/projects/{project_name}/ps", response_model=ComposePsResponse)
@inject
async def compose_ps(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    all: bool = Query(False),  # noqa: A002
    _principal: Principal = Security(get_current_principal),
) -> ComposePsResponse:
    """List containers for a compose project via ``compose ps``."""
    audit.info(
        "api.v2.compose.projects.ps", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    extra = " -a" if all else ""
    args = f"ps --format json{extra}"
    out = await _run_compose(runner, node_id, project, args)
    containers: list[dict[str, str]] = []
    if out.strip():
        for line in out.splitlines():
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    containers.append({str(k): str(v) for k, v in obj.items()})
            except json.JSONDecodeError:
                continue
    return ComposePsResponse(output=out, containers=containers)


@router.get("/projects/{project_name}/logs", response_model=ComposeLogsResponse)
@inject
async def compose_logs(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    tail: int = Query(100, ge=1, le=10000),
    since: str | None = Query(None),
    services: str | None = Query(None, description="Optional service name"),
    _principal: Principal = Security(get_current_principal),
) -> ComposeLogsResponse:
    """Get logs for a compose project via ``compose logs``."""
    audit.info(
        "api.v2.compose.projects.logs", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    since_arg = f" --since {shlex.quote(since)}" if since else ""
    services_arg = f" {shlex.quote(services)}" if services else ""
    args = f"logs --tail {tail}{since_arg}{services_arg}"
    out = await _run_compose(runner, node_id, project, args)
    return ComposeLogsResponse(output=out, logs=out)


@router.get("/projects/{project_name}/config", response_model=ComposeConfigResponse)
@inject
async def compose_config(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    _principal: Principal = Security(get_current_principal),
) -> ComposeConfigResponse:
    """Return resolved compose config via ``compose config``."""
    audit.info(
        "api.v2.compose.projects.config",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    out = await _run_compose(runner, node_id, project, "config")
    return ComposeConfigResponse(config=out, output=out)


@router.get("/projects/{project_name}/images", response_model=ComposeImagesResponse)
@inject
async def compose_images(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    _principal: Principal = Security(get_current_principal),
) -> ComposeImagesResponse:
    """List images for a compose project via ``compose images``."""
    audit.info(
        "api.v2.compose.projects.images",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    # Try json format, fallback to raw
    try:
        out = await _run_compose(runner, node_id, project, "images --format json")
    except Exception:
        out = await _run_compose(runner, node_id, project, "config --images")
    images: list[str] = []
    if out.strip():
        for line in out.splitlines():
            stripped = line.strip()
            if stripped.startswith("{"):
                try:
                    obj = json.loads(stripped)
                    if isinstance(obj, dict):
                        repo = obj.get("Repository") or obj.get("repository") or ""
                        if isinstance(repo, str) and repo:
                            images.append(repo)
                except json.JSONDecodeError:
                    images.append(stripped)
            elif stripped:
                images.append(stripped)
    return ComposeImagesResponse(images=images, output=out)


@router.get("/projects/{project_name}/top", response_model=ComposeTopResponse)
@inject
async def compose_top(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    service: str | None = Query(None, max_length=100),
    _principal: Principal = Security(get_current_principal),
) -> ComposeTopResponse:
    """Return processes via ``compose top``."""
    audit.info(
        "api.v2.compose.projects.top", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    svc_arg = f" {shlex.quote(service)}" if service else ""
    # compose top does not have json; parse textual
    out = await _run_compose(runner, node_id, project, f"top{svc_arg}")
    titles: list[str] = []
    processes: list[list[str]] = []
    lines = [line for line in out.strip().splitlines() if line.strip()]
    if lines:
        titles = lines[0].split()
        for line in lines[1:]:
            processes.append(line.split())
    return ComposeTopResponse(titles=titles, processes=processes, output=out)


@router.get("/projects/{project_name}/port", response_model=ComposePortResponse)
@inject
async def compose_port(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    service: str = Query(..., min_length=1, max_length=100),
    private_port: str = Query(..., min_length=1, max_length=20),
    _principal: Principal = Security(get_current_principal),
) -> ComposePortResponse:
    """Return port bindings via ``compose port``."""
    audit.info(
        "api.v2.compose.projects.port", node_id=str(node_id), project_name=project_name
    )
    project = await _get_project(session, node_id, project_name)
    args = f"port {shlex.quote(service)} {shlex.quote(private_port)}"
    out = await _run_compose(runner, node_id, project, args)
    return ComposePortResponse(output=out, bindings=out)


@router.get("/projects/{project_name}/version", response_model=ComposeVersionResponse)
@inject
async def compose_version(
    node_id: uuid.UUID,
    project_name: str,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    _principal: Principal = Security(get_current_principal),
) -> ComposeVersionResponse:
    """Return compose version via ``compose version``."""
    audit.info(
        "api.v2.compose.projects.version",
        node_id=str(node_id),
        project_name=project_name,
    )
    project = await _get_project(session, node_id, project_name)
    # version does not need file, but we reuse helper
    node = await runner.get_target(node_id)
    docker_args = "compose version --format json"
    # Some versions require --short or json; fallback
    try:
        cmd = runner.build_command(node, docker_args)
        stdout, stderr, exit_code = await runner.execute(node, cmd)
        raise_for_docker_error(stderr, exit_code)
        out = stdout.strip()
        # parse
        try:
            obj = json.loads(out)
            ver = (
                str(obj.get("version") or obj.get("Version") or out)
                if isinstance(obj, dict)
                else out
            )
        except json.JSONDecodeError:
            ver = out
        return ComposeVersionResponse(version=ver, output=out)
    except Exception:
        # fallback without file
        out = await _run_compose(runner, node_id, project, "version --short")
        return ComposeVersionResponse(version=out.strip(), output=out)


@router.post("/projects/{project_name}/executions", response_model=ComposeExecResponse)
@inject
async def compose_exec(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeExecRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeExecResponse:
    """Execute a command in a compose service via ``compose exec``."""
    audit.info(
        "api.v2.compose.projects.executions",
        node_id=str(node_id),
        project_name=project_name,
        service=data.service,
    )
    project = await _get_project(session, node_id, project_name)
    # -T disable pseudo-tty
    cmd_part = shlex.quote(data.command)
    args = f"exec -T {shlex.quote(data.service)} sh -c {cmd_part}"
    out = await _run_compose(runner, node_id, project, args, timeout=data.timeout)
    # For compose exec, exit code is propagated via error; assume 0 on success
    return ComposeExecResponse(stdout=out, stderr="", exit_code=0)


@router.post("/projects/{project_name}/runs", response_model=ComposeRunResponse)
@inject
async def compose_run(
    node_id: uuid.UUID,
    project_name: str,
    data: ComposeRunRequest,
    session: FromDishka[AsyncSession],
    runner: FromDishka[DockerCommandRunner],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> ComposeRunResponse:
    """Run a one-off command via ``compose run``."""
    audit.info(
        "api.v2.compose.projects.runs",
        node_id=str(node_id),
        project_name=project_name,
        service=data.service,
    )
    project = await _get_project(session, node_id, project_name)
    detached = " -d" if data.detached else " --rm"
    cmd_part = f" {shlex.quote(data.command)}" if data.command else ""
    args = f"run{detached} {shlex.quote(data.service)}{cmd_part}"
    out = await _run_compose(runner, node_id, project, args, timeout=data.timeout)
    return ComposeRunResponse(output=out)
