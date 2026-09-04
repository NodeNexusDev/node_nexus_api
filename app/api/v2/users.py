"""User management API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Security, status

from app.api.deps import require_superuser
from app.application.dto.user import UserUpdateDTO, UserViewDTO
from app.application.services.user_service import UserService
from app.schemas.auth import UserCreate, UserListResponse, UserResponse, UserUpdate

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/users", tags=["users"], route_class=DishkaRoute)


def _user_response(user: UserViewDTO) -> UserResponse:
    """Convert user DTO to response schema."""
    return UserResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
    )


@router.get("/", response_model=UserListResponse)
@inject
async def get_users(
    service: FromDishka[UserService],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _key: uuid.UUID = Security(require_superuser),
) -> UserListResponse:
    """List one page of users (superuser only)."""
    audit.info("api.users.list", page=page, size=size)
    result = await service.list_users(
        offset=(page - 1) * size,
        limit=size,
        caller_is_superuser=True,
    )
    return UserListResponse(
        items=[_user_response(user) for user in result.items],
        total=result.total,
    )


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@inject
async def create_user(
    data: UserCreate,
    service: FromDishka[UserService],
    _key: uuid.UUID = Security(require_superuser),
) -> UserResponse:
    """Create a new user (superuser only)."""
    audit.info("api.users.create", email=data.email)
    result = await service.create_user(
        email=data.email,
        password=data.password,
        is_superuser=data.is_superuser,
        caller_is_superuser=True,
    )
    return _user_response(result)


@router.get("/{user_id}", response_model=UserResponse)
@inject
async def get_user(
    user_id: uuid.UUID,
    service: FromDishka[UserService],
    _key: uuid.UUID = Security(require_superuser),
) -> UserResponse:
    """Get one user by id (superuser only)."""
    audit.info("api.users.get", user_id=str(user_id))
    user = await service.get_user(user_id, caller_is_superuser=True)
    return _user_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
@inject
async def patch_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    service: FromDishka[UserService],
    _key: uuid.UUID = Security(require_superuser),
) -> UserResponse:
    """Patch all mutable user fields (superuser only)."""
    audit.info("api.users.patch", user_id=str(user_id))
    dto = UserUpdateDTO(
        email=data.email,
        password=data.password,
        is_active=data.is_active,
        is_superuser=data.is_superuser,
    )
    try:
        updated = await service.patch_user(user_id, dto, caller_is_superuser=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _user_response(updated)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def delete_user(
    user_id: uuid.UUID,
    service: FromDishka[UserService],
    _key: uuid.UUID = Security(require_superuser),
) -> None:
    """Delete a user (superuser only)."""
    audit.info("api.users.delete", user_id=str(user_id))
    await service.delete_user(user_id, caller_is_superuser=True)
