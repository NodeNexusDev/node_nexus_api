"""Configuration export/import endpoints."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.schemas.config import ConfigExport, ConfigImport, ImportResult
from app.services.config_service import ConfigService

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
    return await service.export_all()


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
    return await service.import_config(data)
