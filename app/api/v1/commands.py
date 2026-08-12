"""Command API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.command_execution import CommandResultDTO
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandExecuteRequestDTO,
    CommandParameterDTO,
    CommandUpdateDTO,
    CommandViewDTO,
)
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_management_service import CommandManagementService
from app.schemas.command import (
    CommandCreate,
    CommandExecuteRequest,
    CommandParameter,
    CommandResponse,
    CommandResult,
    CommandUpdate,
)
from app.schemas.node import PaginatedResponse

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/commands", tags=["commands"], route_class=DishkaRoute)


def _parameter_dto(parameter: CommandParameter) -> CommandParameterDTO:
    return CommandParameterDTO(
        name=parameter.name,
        type=parameter.type,
        required=parameter.required,
        default=parameter.default,
        description=parameter.description,
    )


def _command_response(command: CommandViewDTO) -> CommandResponse:
    return CommandResponse(
        id=command.id,
        name=command.name,
        description=command.description,
        command=command.command,
        parameters=[
            CommandParameter(
                name=parameter.name,
                type=parameter.type,
                required=parameter.required,
                default=parameter.default,
                description=parameter.description,
            )
            for parameter in command.parameters
        ],
        tags=list(command.tags),
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


@router.get("/", response_model=PaginatedResponse[CommandResponse])
@inject
async def get_commands(
    service: FromDishka[CommandManagementService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tag: str | None = Query(None, description="Filter by tag (AND)"),
    search: str | None = Query(None, description="Search by name or description"),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[CommandResponse]:
    """Get all commands with pagination and optional search."""
    tag_list = [t.strip() for t in tag.split(",")] if tag else None
    audit.info(
        "api.commands.list",
        page=page,
        size=size,
        tags=tag_list,
        search=search,
    )
    commands, total = await service.get_all_commands(
        page=page,
        size=size,
        tags=tag_list,
        search=search,
    )
    return PaginatedResponse(
        items=[_command_response(command) for command in commands],
        total=total,
        page=page,
        size=size,
    )


@router.get("/tags", response_model=list[str])
@inject
async def get_command_tags(
    service: FromDishka[CommandManagementService],
    _key: str = Security(get_current_api_key),
) -> list[str]:
    """Get all unique tags across all command templates."""
    audit.info("api.commands.tags.list")
    return await service.get_all_tags()


@router.get("/{command_id}", response_model=CommandResponse)
@inject
async def get_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
    _key: str = Security(get_current_api_key),
) -> CommandResponse:
    """Get a command by ID."""
    audit.info("api.commands.get", command_id=str(command_id))
    return _command_response(await service.get_command(command_id))


@router.post("/", response_model=CommandResponse, status_code=201)
@inject
async def create_command(
    data: CommandCreate,
    service: FromDishka[CommandManagementService],
    _key: str = Security(require_write_scope),
) -> CommandResponse:
    """Create a new command template."""
    audit.info("api.commands.create", name=data.name)
    result = await service.create_command(
        CommandCreateDTO(
            name=data.name,
            description=data.description,
            command=data.command,
            parameters=tuple(_parameter_dto(item) for item in data.parameters),
            tags=tuple(data.tags),
        )
    )
    return _command_response(result)


@router.put("/{command_id}", response_model=CommandResponse)
@inject
async def update_command(
    command_id: uuid.UUID,
    data: CommandUpdate,
    service: FromDishka[CommandManagementService],
    _key: str = Security(require_write_scope),
) -> CommandResponse:
    """Update an existing command template."""
    audit.info("api.commands.update", command_id=str(command_id))
    changes = data.model_dump(exclude_unset=True)
    if isinstance(changes.get("parameters"), list):
        changes["parameters"] = tuple(
            CommandParameterDTO(**parameter) for parameter in changes["parameters"]
        )
    if isinstance(changes.get("tags"), list):
        changes["tags"] = tuple(changes["tags"])
    result = await service.update_command(
        command_id,
        CommandUpdateDTO(changes=tuple(changes.items())),
    )
    return _command_response(result)


@router.delete("/{command_id}", status_code=204)
@inject
async def delete_command(
    command_id: uuid.UUID,
    service: FromDishka[CommandManagementService],
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
    service: FromDishka[CommandExecutionService],
    _key: str = Security(require_write_scope),
) -> CommandResult:
    """Execute a command template on a node."""
    audit.info(
        "api.commands.execute",
        command_id=str(command_id),
        node_id=str(data.node_id),
    )
    result: CommandResultDTO = await service.execute_command(
        command_id,
        CommandExecuteRequestDTO(
            node_id=data.node_id,
            params=tuple(data.params.items()),
        ),
    )
    return CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
    )
