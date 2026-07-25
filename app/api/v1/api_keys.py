"""API key management endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security

from app.api.deps import get_current_api_key
from app.core.exceptions import APIKeyNotFoundError
from app.schemas.api_key import (
    APIKeyCreate,
    APIKeyCreated,
    APIKeyList,
    APIKeyResponse,
    APIKeyUpdate,
)
from app.services.api_key_service import APIKeyService

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/api-keys", tags=["api-keys"], route_class=DishkaRoute)


@router.post("/", response_model=APIKeyCreated, status_code=201)
@inject
async def create_api_key(
    data: APIKeyCreate,
    service: FromDishka[APIKeyService],
    _key: str = Security(get_current_api_key),
) -> APIKeyCreated:
    """Create a new API key. The full key is returned only once."""
    audit.info("api.api_keys.create", name=data.name)
    return await service.create_api_key(data.name)


@router.get("/", response_model=APIKeyList)
@inject
async def list_api_keys(
    service: FromDishka[APIKeyService],
    _key: str = Security(get_current_api_key),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> APIKeyList:
    """List all API keys."""
    audit.info("api.api_keys.list", page=page, size=size)
    return await service.list_api_keys(page=page, size=size)


@router.patch("/{key_id}", response_model=APIKeyResponse)
@inject
async def update_api_key(
    key_id: uuid.UUID,
    data: APIKeyUpdate,
    service: FromDishka[APIKeyService],
    _key: str = Security(get_current_api_key),
) -> APIKeyResponse:
    """Update an API key (name, is_active, scope, expires_at)."""
    audit.info("api.api_keys.update", key_id=str(key_id))
    try:
        return await service.update_api_key(key_id, data)
    except APIKeyNotFoundError:
        raise HTTPException(status_code=404, detail="API key not found")


@router.delete("/{key_id}", status_code=204)
@inject
async def revoke_api_key(
    key_id: uuid.UUID,
    service: FromDishka[APIKeyService],
    _key: str = Security(get_current_api_key),
) -> None:
    """Revoke an API key."""
    audit.info("api.api_keys.revoke", key_id=str(key_id))
    try:
        await service.revoke_api_key(key_id)
    except APIKeyNotFoundError:
        raise HTTPException(status_code=404, detail="API key not found")
