"""Favorites API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.favorite import FavoriteCreateDTO
from app.application.services.favorite_service import FavoriteService
from app.schemas.favorite import FavoriteCreate, FavoriteResponse
from app.schemas.node import PaginatedResponse

audit = structlog.get_logger("audit")

router = APIRouter(tags=["favorites"], route_class=DishkaRoute)


@router.get("/favorites", response_model=PaginatedResponse[FavoriteResponse])
@inject
async def list_favorites(
    service: FromDishka[FavoriteService],
    target_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: str = Security(get_current_api_key),
) -> PaginatedResponse[FavoriteResponse]:
    audit.info("api.favorites.list", target_type=target_type)
    items, total = await service.list_favorites(
        target_type=target_type,
        page=page,
        size=size,
    )
    return PaginatedResponse(
        items=[
            FavoriteResponse(
                id=str(f.id),
                target_type=f.target_type,
                target_id=str(f.target_id),
                name=f.name,
                note=f.note,
                created_at=f.created_at,
            )
            for f in items
        ],
        total=total,
        page=page,
        size=size,
    )


@router.post("/favorites", response_model=FavoriteResponse)
@inject
async def add_favorite(
    data: FavoriteCreate,
    service: FromDishka[FavoriteService],
    _key: str = Security(require_write_scope),
) -> FavoriteResponse:
    audit.info("api.favorites.add", target=data.target_type + ":" + data.target_id)
    result = await service.add_favorite(
        FavoriteCreateDTO(
            target_type=data.target_type,
            target_id=uuid.UUID(data.target_id),
            name=data.name,
            note=data.note,
        )
    )
    return FavoriteResponse(
        id=str(result.id),
        target_type=result.target_type,
        target_id=str(result.target_id),
        name=result.name,
        note=result.note,
        created_at=result.created_at,
    )


@router.delete("/favorites/{target_type}/{target_id}", status_code=204)
@inject
async def remove_favorite(
    target_type: str,
    target_id: str,
    service: FromDishka[FavoriteService],
    _key: str = Security(require_write_scope),
) -> None:
    audit.info("api.favorites.remove", target=target_type + ":" + target_id)
    await service.remove_favorite(target_type, target_id)
