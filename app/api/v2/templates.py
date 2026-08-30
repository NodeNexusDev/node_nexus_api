"""Template API v2 — registries and packs with assets and template_pack_id."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, cast

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security
from pydantic import BaseModel, Field

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
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
from app.schemas.command import CommandCreate
from app.schemas.common import BulkResult, CursorPage
from app.schemas.script import ScriptCreate
from app.schemas.template_pack import PackAssetResponse, PackResponse
from app.schemas.template_registry import (
    RegistryCreate,
    RegistryResponse,
    RegistrySyncItem,
    RegistrySyncResult,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/templates", tags=["templates"], route_class=DishkaRoute)


# ---------------------------------------------------------------------------
# Cursor helpers (offset)
# ---------------------------------------------------------------------------


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


# ---------------------------------------------------------------------------
# Local schemas for v2 (manifest + assets)
# ---------------------------------------------------------------------------


class PackManifestRequest(BaseModel):
    """Manifest for local pack upload."""

    pack_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    version: str = Field(..., min_length=1, max_length=50)
    author: str | None = Field(default=None, max_length=255)
    tags: list[str] = Field(default_factory=list)
    manifest_sha: str | None = Field(default=None, max_length=64)


class PackAssetCreateRequest(BaseModel):
    """Asset with base64 content."""

    path: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)


class PackLocalCreateRequest(BaseModel):
    """Local pack creation (2.0 with assets)."""

    manifest: PackManifestRequest
    commands: list[CommandCreate] = Field(default_factory=list)
    scripts: list[ScriptCreate] = Field(default_factory=list)
    readme: str | None = Field(default=None)
    assets: list[PackAssetCreateRequest] | None = Field(default=None)
    registry_id: uuid.UUID | None = Field(default=None)


class PackDetailWithAssetsResponse(BaseModel):
    """Pack detail with assets."""

    id: uuid.UUID
    registry_id: uuid.UUID | None
    pack_id: str
    name: str
    description: str | None
    version: str
    author: str | None
    tags: list[str] | None
    manifest_sha: str | None
    readme: str | None
    installed_version: str | None
    installed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    assets: list[PackAssetResponse] = Field(default_factory=list)


class PackInstallResult(BaseModel):
    """Single install result."""

    entity_type: Literal["command", "script"]
    entity_id: uuid.UUID | None = None
    name: str
    status: Literal["success", "error"]
    error: str = ""


class PackInstallResponse(BaseModel):
    """Bulk install / update response."""

    pack_id: uuid.UUID
    version: str
    total: int
    succeeded: int
    failed: int
    results: list[PackInstallResult]


class PackInstallationResponse(BaseModel):
    """Single installation link."""

    id: uuid.UUID
    pack_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    created_at: datetime


class StatsBucket(BaseModel):
    """Stats bucket for group_by."""

    group: str
    total: int
    installed: int
    not_installed: int


class PackStatsResponse(BaseModel):
    """Stats response (group_by optional)."""

    total: int
    installed: int
    not_installed: int
    buckets: list[StatsBucket] = Field(default_factory=list)


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
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page_dto = await service.list_registries(offset=offset, limit=limit)
    items = [_registry_response(v) for v in page_dto.items]
    has_more = (offset + len(items)) < page_dto.total
    next_cursor = _encode_offset(offset + limit) if has_more else None
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
            offset = _decode_offset(cursor)
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
    next_cursor = _encode_offset(offset + limit) if has_more else None
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
# Packs — POST /packs/{id}/installations -> 201|207|409 (bulk with template_pack_id)
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
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[PackInstallResult]:
    """Install a pack — bulk create commands/scripts with template_pack_id.

    Returns 201 when all succeed, 207 when partially, 409 when already installed.
    """
    audit.info("api.v2.templates.packs.install", pack_id=str(pack_id))
    try:
        result = await service.install_pack(pack_id)
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


@router.post("/packs/{pack_id}/updates", response_model=BulkResult[PackInstallResult])
@inject
async def update_pack(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[PackInstallResult]:
    """Update a pack via uninstall+install with 207 handling."""
    audit.info("api.v2.templates.packs.update", pack_id=str(pack_id))
    try:
        result = await service.update_pack(pack_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
    else:
        response.status_code = 200
    return bulk


# ---------------------------------------------------------------------------
# Packs — GET /packs/{id}/installations ?cursor&limit
# ---------------------------------------------------------------------------


@router.get(
    "/packs/{pack_id}/installations",
    response_model=CursorPage[PackInstallationResponse],
)
@inject
async def list_installations(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    cursor: str | None = Query(None, description="Opaque cursor"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[PackInstallationResponse]:
    """List installations for a pack with cursor pagination."""
    audit.info(
        "api.v2.templates.packs.installations.list",
        pack_id=str(pack_id),
        cursor=cursor,
        limit=limit,
    )
    offset = 0
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    try:
        page_dto = await service.list_installations(pack_id, offset=offset, limit=limit)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    items = [
        PackInstallationResponse(
            id=item.id,
            pack_id=item.pack_id,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            created_at=item.created_at,
        )
        for item in page_dto.items
    ]
    has_more = (offset + len(items)) < page_dto.total
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[PackInstallationResponse](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )
