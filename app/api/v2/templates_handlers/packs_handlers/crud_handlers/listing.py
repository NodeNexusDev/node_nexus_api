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


@router.get("/packs", response_model=CursorPage[PackResponse])
@inject
async def list_packs(
    service: FromDishka[TemplatePackService],
    cursor: str | None = Query(None, description="Opaque cursor"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    registry_id: Annotated[
        uuid.UUID | None, Query(description="Filter by registry")
    ] = None,
    tag: str | None = Query(None, description="Filter by tag"),
    installed: bool | None = Query(None, description="Filter by installed flag"),
    search: str | None = Query(None, description="Search by name/description"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[PackResponse]:
    """List packs with cursor pagination and filters."""
    audit.info(
        "api.v2.templates.packs.list",
        cursor=cursor,
        limit=limit,
        registry_id=str(registry_id) if registry_id else None,
        tag=tag,
        installed=installed,
    )
    offset = 0
    if cursor is not None:
        try:
            offset = decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page_dto = await service.list_packs(
        PackListQueryDTO(
            offset=offset,
            limit=limit,
            registry_id=registry_id,
            tag=tag,
            installed=installed,
            search=search,
        )
    )
    items = [_pack_response(v) for v in page_dto.items]
    has_more = (offset + len(items)) < page_dto.total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[PackResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Packs — GET /packs/{id} -> detail with assets
# ---------------------------------------------------------------------------


@router.get("/packs/{pack_id}", response_model=PackDetailWithAssetsResponse)
@inject
async def get_pack(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(get_current_principal),
) -> PackDetailWithAssetsResponse:
    """Get pack detail with assets."""
    audit.info("api.v2.templates.packs.get", pack_id=str(pack_id))
    try:
        detail = await service.get_pack_detail(pack_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pack_detail_response(detail)


# ---------------------------------------------------------------------------
# Packs — GET /packs/{id}/archive -> tar streaming (assets)
# ---------------------------------------------------------------------------
