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

router = APIRouter(route_class=DishkaRoute)

# Compatibility aliases for tests importing private helpers
_registry_response = registry_response  # noqa: N816
_pack_response = pack_response  # noqa: N816
_pack_detail_response = pack_detail_response  # noqa: N816


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
    offset = parse_cursor_offset(cursor)
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
    items = [pack_response(v) for v in page_dto.items]
    has_more = (offset + len(items)) < page_dto.total
    from app.api.pagination import encode_offset as _enc

    next_cursor = _enc(offset + limit) if has_more else None
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
