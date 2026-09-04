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


@router.post("/registries", response_model=RegistryResponse, status_code=201)
@inject
async def create_registry(
    data: RegistryCreate,
    service: FromDishka[TemplateRegistryService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> RegistryResponse:
    """Create a template registry (GitHub)."""
    audit.info("api.v2.templates.registries.create", owner=data.owner, name=data.name)
    try:
        view = await service.create_registry(
            RegistryCreateDTO(
                owner=data.owner,
                name=data.name,
                github_token=data.github_token,
                default_branch=data.default_branch or "main",
            )
        )
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _registry_response(view)


# ---------------------------------------------------------------------------
# Registries — GET /registries ?cursor&limit  (cursor)
# ---------------------------------------------------------------------------


@router.get("/registries", response_model=CursorPage[RegistryResponse])
@inject
async def list_registries(
    service: FromDishka[TemplateRegistryService],
    cursor: str | None = Query(None, description="Opaque cursor"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[RegistryResponse]:
    """List registries with cursor pagination."""
    audit.info("api.v2.templates.registries.list", cursor=cursor, limit=limit)
    offset = 0
    if cursor is not None:
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page_dto = await service.list_registries(offset=offset, limit=limit)
    items = [_registry_response(v) for v in page_dto.items]
    has_more = (offset + len(items)) < page_dto.total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[RegistryResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Registries — GET /registries/{id}
# ---------------------------------------------------------------------------


@router.get("/registries/{registry_id}", response_model=RegistryResponse)
@inject
async def get_registry(
    registry_id: uuid.UUID,
    service: FromDishka[TemplateRegistryService],
    _principal: Principal = Security(get_current_principal),
) -> RegistryResponse:
    """Get registry by ID."""
    audit.info("api.v2.templates.registries.get", registry_id=str(registry_id))
    try:
        view = await service.get_registry(registry_id)
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _registry_response(view)


# ---------------------------------------------------------------------------
# Registries — DELETE /registries/{id} -> 204
# ---------------------------------------------------------------------------


@router.delete("/registries/{registry_id}", status_code=204)
@inject
async def delete_registry(
    registry_id: uuid.UUID,
    service: FromDishka[TemplateRegistryService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a registry."""
    audit.info("api.v2.templates.registries.delete", registry_id=str(registry_id))
    try:
        await service.delete_registry(registry_id)
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Registries — POST /registries/{id}/syncs -> 200|207
# ---------------------------------------------------------------------------


@router.post("/registries/{registry_id}/syncs", response_model=RegistrySyncResult)
@inject
async def sync_registry(
    registry_id: uuid.UUID,
    service: FromDishka[TemplateRegistryService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> RegistrySyncResult:
    """Sync packs from a registry (200|207)."""
    audit.info("api.v2.templates.registries.sync", registry_id=str(registry_id))
    try:
        result = await service.sync_registry(registry_id)
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result.failed > 0 and result.succeeded > 0:
        response.status_code = 207
    items = [
        RegistrySyncItem(
            pack_id=item.pack_id,
            status=cast(Literal["success", "error"], item.status),
            error=item.error,
            message=item.message,
        )
        for item in result.results
    ]
    return RegistrySyncResult(
        registry_id=result.registry_id,
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        results=items,
    )


# ---------------------------------------------------------------------------
# Packs — POST /packs {manifest, commands, scripts, readme?, assets?} -> 201 local
# ---------------------------------------------------------------------------
