"""Authentication application service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.application.dto.user import UserViewDTO
from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError, TokenExpiredError

if TYPE_CHECKING:
    from app.application.ports.jwt_handler import JWTHandler
    from app.application.ports.password_hasher import PasswordHasher
    from app.application.ports.refresh_token_persistence import (
        RefreshTokenReader,
        RefreshTokenWriter,
    )
    from app.application.ports.user_persistence import UserReader

audit = structlog.get_logger("audit")


class AuthService:
    """Handle JWT authentication flows."""

    def __init__(
        self,
        user_reader: UserReader,
        refresh_reader: RefreshTokenReader,
        refresh_writer: RefreshTokenWriter,
        jwt_handler: JWTHandler,
        password_hasher: PasswordHasher,
    ) -> None:
        self._user_reader = user_reader
        self._refresh_reader = refresh_reader
        self._refresh_writer = refresh_writer
        self._jwt = jwt_handler
        self._password_hasher = password_hasher

    async def login(self, email: str, password: str) -> dict[str, str]:
        """Authenticate user and return tokens.

        Returns:
            Dict with access_token, refresh_token, and token_type.

        Raises:
            InvalidCredentialsError: Invalid email or password.
        """
        user_id = await self._user_reader.get_user_id_by_email(email)
        if user_id is None:
            raise InvalidCredentialsError("Invalid email or password")

        hashed = await self._user_reader.get_hashed_password(email)
        if hashed is None or not self._password_hasher.verify(password, hashed):
            raise InvalidCredentialsError("Invalid email or password")

        if not await self._user_reader.is_user_active(user_id):
            raise InvalidCredentialsError("Invalid email or password")

        # Cleanup expired refresh tokens for this user
        await self._refresh_writer.delete_expired_by_user(user_id)

        # Generate tokens
        access_token = self._jwt.encode_access_token(
            str(user_id), email, await self._user_reader.is_superuser(user_id)
        )
        refresh_token = self._jwt.encode_refresh_token(str(user_id))

        # Store refresh token hash
        settings = get_settings()
        expires_at = datetime.now(UTC) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        token_hash = self._jwt.hash_token(refresh_token)
        await self._refresh_writer.create(user_id, token_hash, expires_at)

        audit.info("auth.login.ok", user_id=str(user_id))
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",  # nosec B105 — OAuth2 token type, not a password
        }

    async def refresh_access_token(self, refresh_token_hash: str) -> dict[str, str]:
        """Validate refresh token and return new token pair.

        Raises:
            TokenExpiredError: Refresh token is expired or invalid.
            InvalidCredentialsError: User is inactive.
        """
        user_id = await self._refresh_reader.get_by_hash(refresh_token_hash)
        if user_id is None:
            raise TokenExpiredError("Invalid or expired refresh token")

        if not await self._user_reader.is_user_active(user_id):
            raise InvalidCredentialsError("User is inactive")

        # Delete old refresh token (rotation)
        await self._refresh_writer.delete(refresh_token_hash)

        # Load user info for new tokens
        user = await self._user_reader.get_user(user_id)
        if user is None:
            raise TokenExpiredError("User not found")

        # Generate new tokens
        access_token = self._jwt.encode_access_token(
            str(user_id), user.email, user.is_superuser
        )
        refresh_token = self._jwt.encode_refresh_token(str(user_id))

        # Store new refresh token hash
        settings = get_settings()
        expires_at = datetime.now(UTC) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        token_hash = self._jwt.hash_token(refresh_token)
        await self._refresh_writer.create(user_id, token_hash, expires_at)

        audit.info("auth.refresh.ok", user_id=str(user_id))
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",  # nosec B105 — OAuth2 token type, not a password
        }

    async def logout(self, refresh_token_hash: str) -> None:
        """Delete refresh token."""
        await self._refresh_writer.delete(refresh_token_hash)
        audit.info("auth.logout.ok")

    async def get_current_user(self, user_id: UUID) -> UserViewDTO:
        """Get current user from JWT claims.

        Raises:
            InvalidCredentialsError: User not found or inactive.
        """
        user = await self._user_reader.get_user(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")
        if not user.is_active:
            raise InvalidCredentialsError("User is inactive")
        return user
