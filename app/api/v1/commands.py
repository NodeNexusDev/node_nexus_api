"""Command API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
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
    tag: str | None = Query(None, description="Filter by tag (AND)"),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[CommandResponse]:
    """Get all commands with pagination."""
    tag_list = [t.strip() for t in tag.split(",")] if tag else None
    audit.info("api.commands.list", page=page, size=size, tags=tag_list)
    commands, total = await service.get_all_commands(
        page=page, size=size, tags=tag_list
    )
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
    return await service.get_command(command_id)


@router.post("/", response_model=CommandResponse, status_code=201)
@inject
async def create_command(
    data: CommandCreate,
    service: FromDishka[CommandService],
    _key: str = Security(require_write_scope),
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
    _key: str = Security(require_write_scope),
) -> CommandResponse:
    """Update an existing command template."""
    audit.info("api.commands.update", command_id=str(command_id))
    return await service.update_command(command_id, data)


@router.delete("/{command_id}", status_code=204)
@inject
async def delete_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandService],
    _key: str = Security(require_write_scope),
) -> None:
    """Delete a command template."""
    audit.info("api.commands.delete", command_id=str(command_id))
    await service.delete_command(command_id)


@router.post("/{command_id}/execute", response_model=CommandResult)
@inject
async def execute_command(
    command_id: uuid.UUID,
    data: CommandExecuteRequest,
    service: FromDishka[CommandService],
    _key: str = Security(require_write_scope),
) -> CommandResult:
    """Execute a command template on a node."""
    audit.info(
        "api.commands.execute",
        command_id=str(command_id),
        node_id=str(data.node_id),
    )
    return await service.execute_command(command_id, data)
