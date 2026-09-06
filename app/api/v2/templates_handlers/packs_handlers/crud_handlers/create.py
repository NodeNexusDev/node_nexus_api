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


@router.post("/packs", response_model=PackDetailWithAssetsResponse, status_code=201)
@inject
async def create_pack(
    data: PackLocalCreateRequest,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> PackDetailWithAssetsResponse:
    """Create a local template pack with assets (201)."""
    audit.info(
        "api.v2.templates.packs.create",
        pack_id=data.manifest.pack_id,
        assets=len(data.assets or []),
    )
    manifest_dto = ManifestDTO(
        pack_id=data.manifest.pack_id,
        name=data.manifest.name,
        description=data.manifest.description,
        version=data.manifest.version,
        author=data.manifest.author,
        tags=tuple(data.manifest.tags or []),
        manifest_sha=data.manifest.manifest_sha,
    )
    assets_dto = tuple(
        PackAssetCreateDTO(path=a.path, content_base64=a.content_base64)
        for a in (data.assets or [])
    )
    # commands/scripts stored as raw objects (Pydantic models -> dict)
    commands_raw: tuple[object, ...] = tuple(
        c.model_dump() if hasattr(c, "model_dump") else c for c in data.commands
    )
    scripts_raw: tuple[object, ...] = tuple(
        s.model_dump() if hasattr(s, "model_dump") else s for s in data.scripts
    )
    try:
        detail = await service.create_pack(
            PackCreateDTO(
                manifest=manifest_dto,
                commands=commands_raw,
                scripts=scripts_raw,
                readme=data.readme,
                assets=assets_dto,
                registry_id=data.registry_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        # DomainError maps to 422 via handler, but local create conflict -> 409
        if "already exists" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _pack_detail_response(detail)


# ---------------------------------------------------------------------------
# Packs — GET /packs/stats ?group_by=   (must be before /packs/{id})
# ---------------------------------------------------------------------------


@router.get("/packs/stats", response_model=PackStatsResponse)
@inject
async def get_packs_stats(
    service: FromDishka[TemplatePackService],
    group_by: str | None = Query(None, description="Group by field"),
    _principal: Principal = Security(get_current_principal),
) -> PackStatsResponse:
    """Get pack stats with optional group_by."""
    audit.info("api.v2.templates.packs.stats", group_by=group_by)
    stats = await service.get_stats(group_by=group_by)
    buckets = [
        StatsBucket(
            group=b.group,
            total=b.total,
            installed=b.installed,
            not_installed=b.not_installed,
        )
        for b in stats.buckets
    ]
    return PackStatsResponse(
        total=stats.total,
        installed=stats.installed,
        not_installed=stats.not_installed,
        buckets=buckets,
    )


# ---------------------------------------------------------------------------
# Packs — GET /packs ?cursor&limit&registry_id&tag&installed?
# ---------------------------------------------------------------------------
