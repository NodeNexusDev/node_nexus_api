"""User management application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from app.application.dto.user import (
    UserCreateDTO,
    UserPageDTO,
    UserUpdateDTO,
    UserViewDTO,
)
from app.core.exceptions import (
    InsufficientPermissionsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)

if TYPE_CHECKING:
    from app.application.ports.user_persistence import UserReader, UserWriter

audit = structlog.get_logger("audit")


class UserService:
    """Manage users through application persistence ports."""

    def __init__(
        self,
        reader: UserReader,
        writer: UserWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def create_user(
        self,
        email: str,
        password: str,
        is_superuser: bool = False,
        *,
        caller_is_superuser: bool = False,
    ) -> UserViewDTO:
        """Create a new user.

        Raises:
            InsufficientPermissionsError: Caller is not superuser.
            UserAlreadyExistsError: Email already exists.
        """
        if not caller_is_superuser:
            raise InsufficientPermissionsError("Only superusers can create users")

        existing = await self._reader.get_by_email(email)
        if existing is not None:
            raise UserAlreadyExistsError(f"User with email '{email}' already exists")

        result = await self._writer.create_user(
            UserCreateDTO(email=email, password=password, is_superuser=is_superuser)
        )
        audit.info("user.create.ok", user_id=str(result.id), email=email)
        return result

    async def list_users(
        self,
        offset: int,
        limit: int,
        *,
        caller_is_superuser: bool = False,
    ) -> UserPageDTO:
        """List all users.

        Raises:
            InsufficientPermissionsError: Caller is not superuser.
        """
        if not caller_is_superuser:
            raise InsufficientPermissionsError("Only superusers can list users")
        users = await self._reader.list_users(offset, limit)
        total = await self._reader.count_users()
        return UserPageDTO(items=tuple(users), total=total)

    async def get_user(
        self, user_id: UUID, *, caller_is_superuser: bool = False
    ) -> UserViewDTO:
        """Get one user by id."""
        if not caller_is_superuser:
            raise InsufficientPermissionsError("Only superusers can get users")
        user = await self._reader.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        return user

    async def patch_user(
        self,
        user_id: UUID,
        data: UserUpdateDTO,
        *,
        caller_is_superuser: bool = False,
    ) -> UserViewDTO:
        """Patch all mutable fields (email, password, is_active, is_superuser)."""
        if not caller_is_superuser:
            raise InsufficientPermissionsError("Only superusers can update users")
        # email uniqueness
        if data.email is not None:
            existing = await self._reader.get_by_email(data.email)
            if existing is not None and existing.id != user_id:
                raise UserAlreadyExistsError(
                    f"User with email '{data.email}' already exists"
                )
        updated = await self._writer.update_user(user_id, data)
        if updated is None:
            raise UserNotFoundError(f"User {user_id} not found")
        audit.info("user.patch.ok", user_id=str(user_id))
        return updated

    async def delete_user(
        self, user_id: UUID, *, caller_is_superuser: bool = False
    ) -> bool:
        """Delete a user.

        Raises:
            InsufficientPermissionsError: Caller is not superuser.
            UserNotFoundError: User not found.
        """
        if not caller_is_superuser:
            raise InsufficientPermissionsError("Only superusers can delete users")

        user = await self._reader.get_user(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")

        result = await self._writer.delete_user(user_id)
        audit.info("user.delete.ok", user_id=str(user_id))
        return result
