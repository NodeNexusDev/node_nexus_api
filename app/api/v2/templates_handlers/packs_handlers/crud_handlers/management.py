# ruff: noqa: F401, I001
"""Template packs — PATCH/DELETE management."""

from __future__ import annotations

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Response, Security

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.dto.template_pack import PackUpdateDTO, PackViewDTO
from app.application.services.template_pack_service import (
    PackNotFoundError,
    TemplatePackService,
)
from app.schemas.common import BulkResult
from app.schemas.template_pack import (
    BulkPackDeleteRequest,
    BulkPackDeleteResponse,
    BulkPackDeleteResult,
    PackResponse,
    PackUpdate,
)

audit = structlog.get_logger("audit")

router = APIRouter(route_class=DishkaRoute)


def _pack_response(view: PackViewDTO) -> PackResponse:
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


@router.patch("/packs/{pack_id}", response_model=PackResponse)
@inject
async def patch_pack(
    pack_id: uuid.UUID,
    data: PackUpdate,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> PackResponse:
    """Partially update pack metadata (name, description, version, tags, etc.)."""
    audit.info("api.v2.templates.packs.patch", pack_id=str(pack_id))
    dto = PackUpdateDTO(
        name=data.name,
        description=data.description,
        version=data.version,
        author=data.author,
        tags=tuple(data.tags) if data.tags is not None else None,
        manifest_sha=data.manifest_sha,
        readme=data.readme,
    )
    try:
        view = await service.patch_pack(pack_id, dto)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _pack_response(view)


@router.delete("/packs/{pack_id}", status_code=204)
@inject
async def delete_pack(
    pack_id: uuid.UUID,
    service: FromDishka[TemplatePackService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Hard delete pack with assets and installations."""
    audit.info("api.v2.templates.packs.delete", pack_id=str(pack_id))
    try:
        await service.delete_pack(pack_id)
    except PackNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/packs/deletions", response_model=BulkPackDeleteResponse)
@inject
async def bulk_delete_packs(
    data: BulkPackDeleteRequest,
    service: FromDishka[TemplatePackService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkPackDeleteResponse:
    """Bulk delete packs (POST for RESTful body, 207 on partial)."""
    audit.info("api.v2.templates.packs.bulk_delete", count=len(data.pack_ids))
    results: list[BulkPackDeleteResult] = []
    for pid in data.pack_ids:
        try:
            await service.delete_pack(pid)
            results.append(BulkPackDeleteResult(pack_id=pid, status="success"))
        except PackNotFoundError as exc:
            results.append(
                BulkPackDeleteResult(pack_id=pid, status="error", error=str(exc))
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                BulkPackDeleteResult(pack_id=pid, status="error", error=str(exc))
            )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkPackDeleteResponse(
        total=len(results), succeeded=succeeded, failed=failed, results=results
    )
