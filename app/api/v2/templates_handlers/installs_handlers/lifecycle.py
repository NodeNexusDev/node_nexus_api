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
# Helpers to map DTO -> response
# ---------------------------------------------------------------------------


def _registry_response(view: Any) -> RegistryResponse:  # noqa: ANN401
    return RegistryResponse(
        id=view.id,
        owner=view.owner,
        name=view.name,
        default_branch=view.default_branch,
        last_synced_at=view.last_synced_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _pack_response(view: Any) -> PackResponse:  # noqa: ANN401
    return PackResponse(
        id=view.id,
        registry_id=view.registry_id,
        pack_id=view.pack_id,
        name=view.name,
        description=view.description,
        version=view.version,
        author=view.author,
        tags=list(view.tags) if view.tags else [],
        manifest_sha=view.manifest_sha,
        readme=view.readme,
        installed_version=view.installed_version,
        installed_at=view.installed_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _pack_detail_response(detail: Any) -> PackDetailWithAssetsResponse:  # noqa: ANN401
    view = detail.pack
    assets = [
        PackAssetResponse(
            id=a.id,
            pack_id=a.pack_id,
            path=a.path,
            size=a.size,
            sha=a.sha,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in detail.assets
    ]
    return PackDetailWithAssetsResponse(
        id=view.id,
        registry_id=view.registry_id,
        pack_id=view.pack_id,
        name=view.name,
        description=view.description,
        version=view.version,
        author=view.author,
        tags=list(view.tags) if view.tags else [],
        manifest_sha=view.manifest_sha,
        readme=view.readme,
        installed_version=view.installed_version,
        installed_at=view.installed_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
        assets=assets,
    )


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

    Returns 201 when all succeed, 207 when partially, 409 when conflict.
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
        # pure failure still 201? keep 201 unless 207; but allow 200 fallback
        response.status_code = 201
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


