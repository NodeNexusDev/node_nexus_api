# ruff: noqa: F401, I001
"""Template API v2 — registries and packs with assets and template_pack_id."""

from __future__ import annotations

import io
import uuid
from typing import Annotated, Any, Literal, cast

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security
from fastapi.responses import StreamingResponse

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.pagination import decode_offset, encode_offset
from app.api.v2._shared import pack_detail_response, pack_response, registry_response
from app.application.dto.template_pack import (
    PackAssetCreateDTO,
    PackCreateDTO,
    PackListQueryDTO,
)
from app.application.dto.template_pack import PackManifestDTO as ManifestDTO
from app.application.dto.template_registry import RegistryCreateDTO
from app.application.services.template_pack_service import (
    PackConflictError,
    PackNotFoundError,
    TemplatePackService,
)
from app.application.services.template_registry_service import (
    RegistryConflictError,
    RegistryNotFoundError,
    TemplateRegistryService,
)
from app.schemas.common import BulkResult, CursorPage
from app.schemas.template_pack import (
    PackAssetResponse,
    PackDetailWithAssetsResponse,
    PackInstallationResponse,
    PackInstallResult,
    PackLocalCreateRequest,
    PackResponse,
    PackStatsResponse,
    StatsBucket,
)
from app.schemas.template_registry import (
    RegistryCreate,
    RegistryResponse,
    RegistrySyncItem,
    RegistrySyncResult,
)

audit = structlog.get_logger("audit")

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

router = APIRouter(route_class=DishkaRoute)


# ---------------------------------------------------------------------------
# Helpers to map DTO -> response (centralized in _shared)
# ---------------------------------------------------------------------------

_pack_response = pack_response  # noqa: N816
_registry_response = registry_response  # noqa: N816
_pack_detail_response = pack_detail_response  # noqa: N816


# ---------------------------------------------------------------------------
# Registries — POST /registries  (201)
# ---------------------------------------------------------------------------


@router.post(
    "/packs/{pack_id}/installations",
    response_model=BulkResult[PackInstallResult],
    status_code=201,
)
@inject
async def install_pack(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    response: Response,
    on_conflict: Literal["fail", "rename"] = Query("fail"),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[PackInstallResult]:
    """Install a pack — bulk create commands/scripts with template_pack_id.

    Query ``on_conflict`` controls name collisions:
    - ``fail`` (default) raises 409 on existing command/script name.
    - ``rename`` generates unique name by appending ``_1``, ``_2`` etc.

    Returns 201 when all succeed, 207 when partially, 409 when conflict,
    422 when all failed.
    """
    audit.info(
        "api.v2.templates.packs.install",
        pack_id=str(pack_id),
        on_conflict=on_conflict,
    )
    try:
        result = await service.install_pack(pack_id, on_conflict=on_conflict)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PackConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    items = [
        PackInstallResult(
            entity_type=cast(Literal["command", "script"], item.entity_type),
            entity_id=item.entity_id,
            name=item.name,
            status=cast(Literal["success", "error"], item.status),
            error=item.error,
        )
        for item in result.results
    ]
    bulk = BulkResult[PackInstallResult](
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        results=items,
    )
    if result.failed > 0 and result.succeeded > 0:
        response.status_code = 207
    elif result.failed > 0 and result.succeeded == 0 and result.total > 0:
        response.status_code = 422
    return bulk


# ---------------------------------------------------------------------------
# Packs — POST /packs/{id}/uninstallations -> 204
# ---------------------------------------------------------------------------


@router.post("/packs/{pack_id}/uninstallations", status_code=204)
@inject
async def uninstall_pack(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Uninstall a pack (204)."""
    audit.info("api.v2.templates.packs.uninstall", pack_id=str(pack_id))
    try:
        await service.uninstall_pack(pack_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Packs — POST /packs/{id}/updates -> 200|207 (uninstall+install)
# ---------------------------------------------------------------------------
