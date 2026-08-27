"""Unit tests for UserService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dto.user import UserCreateDTO, UserViewDTO
from app.application.services.user_service import UserService
from app.core.exceptions import (
    InsufficientPermissionsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)


@pytest.fixture
def reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def writer() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(reader: AsyncMock, writer: AsyncMock) -> UserService:
    return UserService(reader=reader, writer=writer)


def _user_view(**overrides) -> UserViewDTO:
    defaults = {
        "id": uuid4(),
        "email": "test@example.com",
        "is_active": True,
        "is_superuser": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return UserViewDTO(**defaults)


class TestCreateUser:
    async def test_not_superuser(self, service: UserService) -> None:
        with pytest.raises(InsufficientPermissionsError, match="Only superusers"):
            await service.create_user(
                "test@example.com", "pass", caller_is_superuser=False
            )

    async def test_duplicate_email(
        self, service: UserService, reader: AsyncMock
    ) -> None:
        reader.get_by_email.return_value = _user_view()
        with pytest.raises(UserAlreadyExistsError, match="already exists"):
            await service.create_user(
                "test@example.com", "pass", caller_is_superuser=True
            )

    async def test_success(
        self, service: UserService, reader: AsyncMock, writer: AsyncMock
    ) -> None:
        reader.get_by_email.return_value = None
        created = _user_view()
        writer.create_user.return_value = created

        result = await service.create_user(
            "test@example.com", "pass", is_superuser=True, caller_is_superuser=True
        )

        assert result == created
        writer.create_user.assert_called_once()
        call_args = writer.create_user.call_args[0][0]
        assert isinstance(call_args, UserCreateDTO)
        assert call_args.email == "test@example.com"
        assert call_args.is_superuser is True


class TestListUsers:
    async def test_not_superuser(self, service: UserService) -> None:
        with pytest.raises(InsufficientPermissionsError, match="Only superusers"):
            await service.list_users(0, 20, caller_is_superuser=False)

    async def test_success(self, service: UserService, reader: AsyncMock) -> None:
        users = [_user_view(), _user_view(email="other@example.com")]
        reader.list_users.return_value = users
        reader.count_users.return_value = 7
        result = await service.list_users(20, 20, caller_is_superuser=True)
        assert result.items == tuple(users)
        assert result.total == 7
        reader.list_users.assert_awaited_once_with(20, 20)


class TestDeleteUser:
    async def test_not_superuser(self, service: UserService) -> None:
        with pytest.raises(InsufficientPermissionsError, match="Only superusers"):
            await service.delete_user(uuid4(), caller_is_superuser=False)

    async def test_user_not_found(
        self, service: UserService, reader: AsyncMock
    ) -> None:
        reader.get_user.return_value = None
        with pytest.raises(UserNotFoundError, match="not found"):
            await service.delete_user(uuid4(), caller_is_superuser=True)

    async def test_success(
        self, service: UserService, reader: AsyncMock, writer: AsyncMock
    ) -> None:
        user = _user_view()
        reader.get_user.return_value = user
        writer.delete_user.return_value = True

        result = await service.delete_user(user.id, caller_is_superuser=True)

        assert result is True
        writer.delete_user.assert_called_once_with(user.id)
