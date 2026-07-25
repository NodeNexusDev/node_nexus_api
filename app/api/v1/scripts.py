"""Script API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
    ScriptNotFoundError,
    TemplateRenderError,
)
from app.schemas.node import PaginatedResponse
from app.schemas.script import (
    ScriptCreate,
    ScriptExecuteRequest,
    ScriptExecutionBatchResult,
    ScriptResponse,
    ScriptUpdate,
)
from app.schemas.script_execution import ScriptExecutionResponse
from app.services.script_service import ScriptService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/scripts", tags=["scripts"], route_class=DishkaRoute)


@router.get("/", response_model=PaginatedResponse[ScriptResponse])
@inject
async def get_scripts(
    service: FromDishka[ScriptService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None, description="Filter by tag (AND)"),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[ScriptResponse]:
    """Get all scripts with pagination."""
    tag_list = [t.strip() for t in tag.split(",")] if tag else None
    audit.info("api.scripts.list", page=page, size=size, tags=tag_list)
    scripts, total = await service.get_all_scripts(page=page, size=size, tags=tag_list)
    return PaginatedResponse(items=scripts, total=total, page=page, size=size)


@router.get("/{script_id}", response_model=ScriptResponse)
@inject
async def get_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Get a script by ID."""
    audit.info("api.scripts.get", script_id=str(script_id))
    try:
        return await service.get_script(script_id)
    except ScriptNotFoundError:
        audit.warning("api.scripts.not_found", script_id=str(script_id))
        raise HTTPException(status_code=404, detail="Script not found")


@router.post("/", response_model=ScriptResponse, status_code=201)
@inject
async def create_script(
    data: ScriptCreate,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Create a new script."""
    audit.info("api.scripts.create", name=data.name)
    return await service.create_script(data)


@router.put("/{script_id}", response_model=ScriptResponse)
@inject
async def update_script(
    script_id: uuid.UUID,
    data: ScriptUpdate,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptResponse:
    """Update an existing script."""
    audit.info("api.scripts.update", script_id=str(script_id))
    try:
        return await service.update_script(script_id, data)
    except ScriptNotFoundError:
        audit.warning("api.scripts.not_found", script_id=str(script_id))
        raise HTTPException(status_code=404, detail="Script not found")


@router.delete("/{script_id}", status_code=204)
@inject
async def delete_script(
    script_id: uuid.UUID,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> None:
    """Delete a script."""
    audit.info("api.scripts.delete", script_id=str(script_id))
    try:
        await service.delete_script(script_id)
    except ScriptNotFoundError:
        audit.warning("api.scripts.not_found", script_id=str(script_id))
        raise HTTPException(status_code=404, detail="Script not found")


@router.post("/{script_id}/execute", response_model=ScriptExecutionBatchResult)
@inject
async def execute_script(
    script_id: uuid.UUID,
    data: ScriptExecuteRequest,
    service: FromDishka[ScriptService],
    _key: str = Security(get_current_api_key),
) -> ScriptExecutionBatchResult:
    """Execute a script on multiple nodes."""
    audit.info(
        "api.scripts.execute",
        script_id=str(script_id),
        node_count=len(data.node_ids),
    )
    try:
        return await service.execute_script(script_id, data)
    except ScriptNotFoundError:
        audit.warning("api.scripts.not_found", script_id=str(script_id))
        raise HTTPException(status_code=404, detail="Script not found")
    except (NodeNotFoundError, CommandNotFoundError) as exc:
        audit.warning("api.scripts.dependency_not_found", error=str(exc))
        raise HTTPException(status_code=404, detail=str(exc))
    except TemplateRenderError as exc:
        audit.error("api.scripts.render_error", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))
    except ConnectionFailedError as exc:
        audit.error("api.scripts.connection_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{script_id}/executions")
@inject
async def get_executions(
    script_id: uuid.UUID,
    service: FromDishka[ScriptService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[ScriptExecutionResponse]:
    """Get execution history for a script."""
    audit.info("api.scripts.executions", script_id=str(script_id))
    try:
        executions, total = await service.get_executions(
            script_id, page=page, size=size
        )
        return PaginatedResponse(items=executions, total=total, page=page, size=size)
    except ScriptNotFoundError:
        audit.warning("api.scripts.not_found", script_id=str(script_id))
        raise HTTPException(status_code=404, detail="Script not found")
