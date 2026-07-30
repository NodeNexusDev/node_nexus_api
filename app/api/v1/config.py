"""Configuration export/import endpoints."""

from dataclasses import asdict
from datetime import datetime
from typing import cast

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.config import (
    CommandConfigDTO,
    ConfigImportResultDTO,
    ConfigTransferDTO,
    NodeConfigDTO,
    ScriptConfigDTO,
)
from app.application.services.config_service import ConfigService
from app.schemas.config import ConfigExport, ConfigImport, ImportResult

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/config", tags=["config"], route_class=DishkaRoute)


@router.get("/export", response_model=ConfigExport)
@inject
async def export_config(
    service: FromDishka[ConfigService],
    _key: str = Security(get_current_api_key),
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
        nodes=[asdict(item) for item in result.nodes],
        commands=[asdict(item) for item in result.commands],
        scripts=[asdict(item) for item in result.scripts],
    )


@router.post("/import", response_model=ImportResult)
@inject
async def import_config(
    data: ConfigImport,
    service: FromDishka[ConfigService],
    _key: str = Security(require_write_scope),
) -> ImportResult:
    """Import nodes, commands, and scripts configuration.

    Duplicates (by name) are skipped and reported in errors.
    """
    audit.info(
        "api.config.import",
        nodes=len(data.nodes),
        commands=len(data.commands),
        scripts=len(data.scripts),
    )
    result = await service.import_config(
        ConfigTransferDTO(
            format_version=data.format_version,
            application_version=data.application_version,
            legacy_version=data.version,
            nodes=tuple(NodeConfigDTO(**item.model_dump()) for item in data.nodes),
            commands=tuple(
                CommandConfigDTO(
                    **item.model_dump(exclude={"parameters", "tags"}),
                    parameters=tuple(item.parameters or ()),
                    tags=tuple(item.tags),
                )
                for item in data.commands
            ),
            scripts=tuple(
                ScriptConfigDTO(
                    **item.model_dump(exclude={"steps", "tags"}),
                    steps=tuple(item.steps),
                    tags=tuple(item.tags),
                )
                for item in data.scripts
            ),
        )
    )
    return _import_response(result)


def _import_response(result: ConfigImportResultDTO) -> ImportResult:
    return ImportResult(
        nodes_created=result.nodes_created,
        commands_created=result.commands_created,
        scripts_created=result.scripts_created,
        errors=list(result.errors),
    )
