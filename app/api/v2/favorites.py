"""Favorite API v2 — cursor pagination with offset translation."""

from __future__ import annotations

import base64
import json
import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.dto.favorite import FavoriteCreateDTO, FavoriteDTO
from app.application.services.favorite_service import FavoriteService
from app.schemas.common import CursorPage
from app.schemas.favorite import FavoriteCreate, FavoriteResponse

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/favorites", tags=["favorites"], route_class=DishkaRoute)


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


def _favorite_response(dto: FavoriteDTO) -> FavoriteResponse:
    """Map a FavoriteDTO to the HTTP response schema."""
    return FavoriteResponse(
        id=str(dto.id),
        target_type=dto.target_type,
        target_id=str(dto.target_id),
        name=dto.name,
        note=dto.note,
        created_at=dto.created_at,
    )


@router.get("/", response_model=CursorPage[FavoriteResponse])
@inject
async def list_favorites(
    service: FromDishka[FavoriteService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    target_type: str | None = Query(None, description="Filter by target type"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[FavoriteResponse]:
    """List favorites with cursor pagination.

    Cursor encodes an offset. Translated to page/size for the offset-based service.
    """
    offset = 0
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    page = offset // limit + 1 if limit else 1
    audit.info(
        "api.v2.favorites.list", cursor=cursor, limit=limit, target_type=target_type
    )
    items, total = await service.list_favorites(
        target_type=target_type, page=page, size=limit
    )
    has_more = (offset + len(items)) < total
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[FavoriteResponse](
        items=[_favorite_response(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


@router.post("/", response_model=FavoriteResponse, status_code=201)
@inject
async def add_favorite(
    data: FavoriteCreate,
    service: FromDishka[FavoriteService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> FavoriteResponse:
    """Add a favorite (shortcut) to any entity."""
    audit.info(
        "api.v2.favorites.add", target_type=data.target_type, target_id=data.target_id
    )
    try:
        target_uuid = uuid.UUID(data.target_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Invalid target_id, must be UUID"
        ) from exc
    dto = FavoriteCreateDTO(
        target_type=data.target_type,
        target_id=target_uuid,
        name=data.name,
        note=data.note,
    )
    result = await service.add_favorite(dto)
    return _favorite_response(result)


@router.delete("/{target_type}/{target_id}", status_code=204)
@inject
async def remove_favorite(
    target_type: str,
    target_id: str,
    service: FromDishka[FavoriteService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Remove a favorite by target type and target identifier."""
    audit.info("api.v2.favorites.remove", target_type=target_type, target_id=target_id)
    await service.remove_favorite(target_type, target_id)
