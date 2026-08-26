"""Authentication API endpoints."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status

from app.api.deps import _decode_access_token, _extract_bearer_token
from app.application.dto.user import UserViewDTO
from app.application.ports.jwt_handler import JWTHandler
from app.application.services.auth_service import AuthService
from app.core.config import get_settings
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/auth", tags=["auth"], route_class=DishkaRoute)


def _user_response(user: UserViewDTO) -> UserResponse:
    """Convert user DTO to response schema."""
    return UserResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at,
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set refresh token as HttpOnly secure cookie."""
    settings = get_settings()
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear refresh token cookie."""
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=True,
        samesite="lax",
    )


@router.post("/login", response_model=TokenResponse)
@inject
async def login(
    data: LoginRequest,
    service: FromDishka[AuthService],
    response: Response,
) -> TokenResponse:
    """Authenticate user. Refresh token set as HttpOnly cookie."""
    audit.info("api.auth.login", email=data.email)
    result = await service.login(data.email, data.password)

    _set_refresh_cookie(response, result["refresh_token"])

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@inject
async def logout(
    jwt_handler: FromDishka[JWTHandler],
    service: FromDishka[AuthService],
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> None:
    """Logout and clear refresh token cookie."""
    if refresh_token:
        await service.logout(jwt_handler.hash_token(refresh_token))
    _clear_refresh_cookie(response)
    audit.info("api.auth.logout")


@router.post("/refresh", response_model=TokenResponse)
@inject
async def refresh_token(
    jwt_handler: FromDishka[JWTHandler],
    service: FromDishka[AuthService],
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> TokenResponse:
    """Refresh access token using refresh token cookie."""
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie",
        )

    audit.info("api.auth.refresh")
    result = await service.refresh_access_token(jwt_handler.hash_token(refresh_token))

    _set_refresh_cookie(response, result["refresh_token"])

    return TokenResponse(
        access_token=result["access_token"],
        token_type=result["token_type"],
    )


@router.get("/me", response_model=UserResponse)
@inject
async def get_me(
    request: Request,
    service: FromDishka[AuthService],
    jwt_handler: FromDishka[JWTHandler],
) -> UserResponse:
    """Get current authenticated user."""
    token = _extract_bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id, _claims = _decode_access_token(jwt_handler, token)
    user = await service.get_current_user(user_id)
    return _user_response(user)
