"""Configuration export/import endpoints."""

from dataclasses import asdict
from datetime import datetime
from typing import cast

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import (
    Principal,
    get_current_principal,
    require_write_or_jwt_scope,
)
from app.application.dto.config import (
    CommandConfigDTO,
    ConfigImportResultDTO,
    ConfigTransferDTO,
    DryRunPreviewDTO,
    NodeConfigDTO,
    ScriptConfigDTO,
)
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.config_service import ConfigService
from app.core.types import ConnectionType, JsonObject
from app.schemas.command import CommandParameter
from app.schemas.config import (
    ConfigExport,
    ConfigImport,
    DryRunCommandPreview,
    DryRunImportResult,
    DryRunNodePreview,
    DryRunScriptPreview,
    DryRunWouldCreate,
    ImportResult,
)
from app.schemas.script import ScriptStep

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/config", tags=["config"], route_class=DishkaRoute)


def _command_parameter_object(parameter: CommandParameter) -> JsonObject:
    return {
        "name": parameter.name,
        "type": parameter.type,
        "required": parameter.required,
        "default": parameter.default,
        "description": parameter.description,
    }


def _script_step_object(step: ScriptStep) -> JsonObject:
    return {
        "label": step.label,
        "type": step.type,
        "command": step.command,
        "command_id": str(step.command_id) if step.command_id else None,
        "params": step.params,
        "on_failure": step.on_failure,
    }


@router.get("/export", response_model=ConfigExport)
@inject
async def export_config(
    service: FromDishka[ConfigService],
    _key: Principal = Security(get_current_principal),
) -> ConfigExport:
    """Export all nodes, commands, and scripts configuration.

    Secrets (passwords, SSH keys) are excluded from the export.
    """
    audit.info("api.config.export")
    result = await service.export_all()
    return ConfigExport(
        format_version=result.format_version or "1.0",
        application_version=result.application_version or "unknown",
        version=result.legacy_version or "0.5.0",
        exported_at=cast(datetime, result.exported_at),
        nodes=[
            {
                "name": n.name,
                "host": n.endpoint.host,
                "port": n.endpoint.port,
                "connection_type": n.endpoint.connection_type,
                "username": n.credentials.username,
                "docker_host": n.endpoint.docker_host,
                "tags": list(n.tags),
            }
            for n in result.nodes
        ],
        commands=[asdict(item) for item in result.commands],
        scripts=[asdict(item) for item in result.scripts],
    )


@router.post("/import", response_model=ImportResult | DryRunImportResult)
@inject
async def import_config(
    data: ConfigImport,
    service: FromDishka[ConfigService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> ImportResult | DryRunImportResult:
    """Import nodes, commands, and scripts configuration.

    Set `dry_run=true` to preview what would be imported without writing.
    Duplicates (by name) are skipped and reported in errors.
    """
    audit.info(
        "api.config.import",
        nodes=len(data.nodes),
        commands=len(data.commands),
        scripts=len(data.scripts),
        dry_run=data.dry_run,
    )
    result = await service.import_config(
        ConfigTransferDTO(
            format_version=data.format_version,
            application_version=data.application_version,
            legacy_version=data.version,
            nodes=tuple(
                NodeConfigDTO(
                    name=item.name,
                    endpoint=NodeEndpoint(
                        host=item.host,
                        port=item.port,
                        connection_type=item.connection_type,
                        docker_host=item.docker_host,
                    ),
                    credentials=NodeCredentials(username=item.username),
                    tags=tuple(item.tags or ()),
                )
                for item in data.nodes
            ),
            commands=tuple(
                CommandConfigDTO(
                    **item.model_dump(exclude={"parameters", "tags"}),
                    parameters=tuple(
                        _command_parameter_object(parameter)
                        for parameter in (item.parameters or ())
                    ),
                    tags=tuple(item.tags),
                )
                for item in data.commands
            ),
            scripts=tuple(
                ScriptConfigDTO(
                    **item.model_dump(exclude={"steps", "tags"}),
                    steps=tuple(_script_step_object(step) for step in item.steps),
                    tags=tuple(item.tags),
                )
                for item in data.scripts
            ),
        ),
        dry_run=data.dry_run,
    )
    if isinstance(result, DryRunPreviewDTO):
        return _dry_run_response(result)
    return _import_response(result)


def _import_response(result: ConfigImportResultDTO) -> ImportResult:
    return ImportResult(
        nodes_created=result.nodes_created,
        commands_created=result.commands_created,
        scripts_created=result.scripts_created,
        errors=list(result.errors),
    )


def _dry_run_response(result: DryRunPreviewDTO) -> DryRunImportResult:
    return DryRunImportResult(
        dry_run=True,
        would_create=DryRunWouldCreate(
            nodes=[
                DryRunNodePreview(
                    name=n.name,
                    host=n.host,
                    port=n.port,
                    connection_type=cast(ConnectionType, n.connection_type),
                    username=n.username,
                    docker_host=n.docker_host,
                    tags=list(n.tags),
                )
                for n in result.would_create_nodes
            ],
            commands=[
                DryRunCommandPreview(
                    name=c.name,
                    description=c.description,
                    command=c.command,
                    tags=list(c.tags),
                )
                for c in result.would_create_commands
            ],
            scripts=[
                DryRunScriptPreview(
                    name=s.name,
                    description=s.description,
                    tags=list(s.tags),
                )
                for s in result.would_create_scripts
            ],
        ),
        duplicates=list(result.duplicates),
        errors=list(result.errors),
    )
