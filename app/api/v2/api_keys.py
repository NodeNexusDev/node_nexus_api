"""API key management endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import (
    Principal,
    get_current_principal,
    require_write_or_jwt_scope,
)
from app.application.dto.api_key import (
    APIKeyCreateDTO,
    APIKeyCreateResultDTO,
    APIKeyPageDTO,
    APIKeyUpdateDTO,
    APIKeyViewDTO,
)
from app.application.services.api_key_management import APIKeyManagementService
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyCreated,
    APIKeyList,
    APIKeyResponse,
    APIKeyUpdate,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/api-keys", tags=["api-keys"], route_class=DishkaRoute)


def _response(item: APIKeyViewDTO) -> APIKeyResponse:
    return APIKeyResponse(
        id=item.id,
        name=item.name,
        key_prefix=item.key_prefix,
        is_active=item.is_active,
        scope=item.scope,
        created_at=item.created_at,
        last_used_at=item.last_used_at,
        expires_at=item.expires_at,
    )


def _created_response(item: APIKeyCreateResultDTO) -> APIKeyCreated:
    return APIKeyCreated(
        id=item.id,
        name=item.name,
        key=item.plain_key,
        key_prefix=item.key_prefix,
        created_at=item.created_at,
    )


def _list_response(page: APIKeyPageDTO, page_num: int, size: int) -> APIKeyList:
    return APIKeyList(
        items=[_response(item) for item in page.items],
        total=page.total,
        page=page_num,
        size=size,
    )


@router.post("/", response_model=APIKeyCreated, status_code=201)
@inject
async def create_api_key(
    data: APIKeyCreate,
    service: FromDishka[APIKeyManagementService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> APIKeyCreated:
    """Create a new API key. The full key is returned only once."""
    audit.info("api.api_keys.create", name=data.name)
    result = await service.create_api_key(
        APIKeyCreateDTO(name=data.name, scope=data.scope)
    )
    return _created_response(result)


@router.get("/", response_model=APIKeyList)
@inject
async def list_api_keys(
    service: FromDishka[APIKeyManagementService],
    _key: Principal = Security(get_current_principal),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> APIKeyList:
    """List all API keys."""
    audit.info("api.api_keys.list", page=page, size=size)
    return _list_response(
        await service.list_api_keys(page=page, size=size), page_num=page, size=size
    )


@router.patch("/{key_id}", response_model=APIKeyResponse)
@inject
async def update_api_key(
    key_id: uuid.UUID,
    data: APIKeyUpdate,
    service: FromDishka[APIKeyManagementService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> APIKeyResponse:
    """Update an API key (name, is_active, scope, expires_at)."""
    audit.info("api.api_keys.update", key_id=str(key_id))
    result = await service.update_api_key(
        key_id,
        APIKeyUpdateDTO(changes=tuple(data.model_dump(exclude_unset=True).items())),
    )
    return _response(result)


@router.delete("/{key_id}", status_code=204)
@inject
async def revoke_api_key(
    key_id: uuid.UUID,
    service: FromDishka[APIKeyManagementService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Revoke an API key."""
    audit.info("api.api_keys.revoke", key_id=str(key_id))
    await service.revoke_api_key(key_id)
