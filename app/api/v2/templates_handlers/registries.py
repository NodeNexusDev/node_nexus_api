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
from app.api.v2._bulk import HTTP_207_MULTI_STATUS
from app.api.v2._shared import (
    _decode_offset,  # noqa: F401
    _encode_offset,  # noqa: F401
    pack_detail_response,
    pack_response,
    parse_cursor_offset,
    registry_response,
)
from app.application.dto.template_pack import (
    PackAssetCreateDTO,
    PackCreateDTO,
    PackListQueryDTO,
)
from app.application.dto.template_pack import PackManifestDTO as ManifestDTO
from app.application.dto.template_registry import RegistryCreateDTO, RegistryUpdateDTO
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
    RegistryUpdate,
)

audit = structlog.get_logger("audit")

router = APIRouter(route_class=DishkaRoute)

# Compatibility aliases for tests importing private helpers
_pack_response = pack_response  # noqa: N816
_registry_response = registry_response  # noqa: N816
_pack_detail_response = pack_detail_response  # noqa: N816


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
    offset = parse_cursor_offset(cursor)
    page_dto = await service.list_registries(offset=offset, limit=limit)
    items = [registry_response(v) for v in page_dto.items]
    has_more = (offset + len(items)) < page_dto.total
    from app.api.pagination import encode_offset as _enc

    next_cursor = _enc(offset + limit) if has_more else None
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
# Registries — PATCH /registries/{id} -> 200
# ---------------------------------------------------------------------------


@router.patch("/registries/{registry_id}", response_model=RegistryResponse)
@inject
async def patch_registry(
    registry_id: uuid.UUID,
    data: RegistryUpdate,
    service: FromDishka[TemplateRegistryService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> RegistryResponse:
    """Partially update registry (owner, name, token, branch)."""
    audit.info("api.v2.templates.registries.patch", registry_id=str(registry_id))
    try:
        view = await service.patch_registry(
            registry_id,
            RegistryUpdateDTO(
                owner=data.owner,
                name=data.name,
                github_token=data.github_token,
                default_branch=data.default_branch,
            ),
        )
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        response.status_code = HTTP_207_MULTI_STATUS
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
