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


@router.get("/packs/{pack_id}/archive")
@inject
async def get_pack_archive(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Stream pack assets as tar archive.

    Returns ``application/x-tar`` with ``Content-Disposition`` attachment.
    Empty tar if pack has no assets. Persisted via ``TemplateAssetWriter``
    (base64 decode, size/sha) and returned in ``GET /packs/{id}``.
    """
    audit.info("api.v2.templates.packs.archive", pack_id=str(pack_id))
    try:
        data = await service.get_assets_tar(pack_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="{pack_id}.tar"'},
    )


@router.get("/packs/{pack_id}/assets/archive", include_in_schema=False)
@inject
async def get_pack_assets_archive_alias(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(get_current_principal),
) -> Any:  # noqa: ANN401
    """Alias for asset tar streaming (compat)."""
    try:
        data = await service.get_assets_tar(pack_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-tar",
        headers={"Content-Disposition": f'attachment; filename="{pack_id}.tar"'},
    )


# ---------------------------------------------------------------------------
# Packs — POST /packs/{id}/installations -> 201|207|409 (bulk with template_pack_id)
# ---------------------------------------------------------------------------
