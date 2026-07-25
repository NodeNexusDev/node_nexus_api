"""Command API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
    TemplateRenderError,
)
from app.schemas.command import (
    CommandCreate,
    CommandExecuteRequest,
    CommandResponse,
    CommandResult,
    CommandUpdate,
)
from app.schemas.node import PaginatedResponse
from app.services.command_service import CommandService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/commands", tags=["commands"], route_class=DishkaRoute)


@router.get("/", response_model=PaginatedResponse[CommandResponse])
@inject
async def get_commands(
    service: FromDishka[CommandService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[CommandResponse]:
    """Get all commands with pagination."""
    audit.info("api.commands.list", page=page, size=size)
    commands, total = await service.get_all_commands(page=page, size=size)
    return PaginatedResponse(items=commands, total=total, page=page, size=size)


@router.get("/{command_id}", response_model=CommandResponse)
@inject
async def get_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandService],
    _key: str = Security(get_current_api_key),
) -> CommandResponse:
    """Get a command by ID."""
    audit.info("api.commands.get", command_id=str(command_id))
    try:
        return await service.get_command(command_id)
    except CommandNotFoundError:
        audit.warning("api.commands.not_found", command_id=str(command_id))
        raise HTTPException(status_code=404, detail="Command not found")


@router.post("/", response_model=CommandResponse, status_code=201)
@inject
async def create_command(
    data: CommandCreate,
    service: FromDishka[CommandService],
    _key: str = Security(get_current_api_key),
) -> CommandResponse:
    """Create a new command template."""
    audit.info("api.commands.create", name=data.name)
    return await service.create_command(data)


@router.put("/{command_id}", response_model=CommandResponse)
@inject
async def update_command(
    command_id: uuid.UUID,
    data: CommandUpdate,
    service: FromDishka[CommandService],
    _key: str = Security(get_current_api_key),
) -> CommandResponse:
    """Update an existing command template."""
    audit.info("api.commands.update", command_id=str(command_id))
    try:
        return await service.update_command(command_id, data)
    except CommandNotFoundError:
        audit.warning("api.commands.not_found", command_id=str(command_id))
        raise HTTPException(status_code=404, detail="Command not found")


@router.delete("/{command_id}", status_code=204)
@inject
async def delete_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandService],
    _key: str = Security(get_current_api_key),
) -> None:
    """Delete a command template."""
    audit.info("api.commands.delete", command_id=str(command_id))
    try:
        await service.delete_command(command_id)
    except CommandNotFoundError:
        audit.warning("api.commands.not_found", command_id=str(command_id))
        raise HTTPException(status_code=404, detail="Command not found")


@router.post("/{command_id}/execute", response_model=CommandResult)
@inject
async def execute_command(
    command_id: uuid.UUID,
    data: CommandExecuteRequest,
    service: FromDishka[CommandService],
    _key: str = Security(get_current_api_key),
) -> CommandResult:
    """Execute a command template on a node."""
    audit.info(
        "api.commands.execute",
        command_id=str(command_id),
        node_id=str(data.node_id),
    )
    try:
        return await service.execute_command(command_id, data)
    except CommandNotFoundError:
        audit.warning("api.commands.not_found", command_id=str(command_id))
        raise HTTPException(status_code=404, detail="Command not found")
    except NodeNotFoundError:
        audit.warning("api.commands.node_not_found", node_id=str(data.node_id))
        raise HTTPException(status_code=404, detail="Node not found")
    except TemplateRenderError as exc:
        audit.error("api.commands.render_error", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc))
    except ConnectionFailedError as exc:
        audit.error("api.commands.connection_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))
