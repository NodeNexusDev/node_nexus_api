"""Unit tests for AuthService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.application.dto.user import UserViewDTO
from app.application.services.auth_service import AuthService
from app.core.exceptions import InvalidCredentialsError, TokenExpiredError


@pytest.fixture
def user_reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def refresh_reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def refresh_writer() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def jwt_handler() -> MagicMock:
    handler = MagicMock()
    handler.encode_access_token.return_value = "access-token-123"
    handler.encode_refresh_token.return_value = "refresh-token-456"
    handler.hash_token.return_value = "hashed-refresh-token"
    return handler


@pytest.fixture
def password_hasher() -> MagicMock:
    hasher = MagicMock()
    hasher.verify.return_value = True
    return hasher


@pytest.fixture
def service(
    user_reader: AsyncMock,
    refresh_reader: AsyncMock,
    refresh_writer: AsyncMock,
    jwt_handler: MagicMock,
    password_hasher: MagicMock,
) -> AuthService:
    return AuthService(
        user_reader=user_reader,
        refresh_reader=refresh_reader,
        refresh_writer=refresh_writer,
        jwt_handler=jwt_handler,
        password_hasher=password_hasher,
    )


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


class TestLogin:
    async def test_invalid_email(
        self, service: AuthService, user_reader: AsyncMock
    ) -> None:
        user_reader.get_user_id_by_email.return_value = None
        with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
            await service.login("wrong@example.com", "password")

    async def test_invalid_password(
        self,
        service: AuthService,
        user_reader: AsyncMock,
        password_hasher: MagicMock,
    ) -> None:
        user = _user_view()
        user_reader.get_user_id_by_email.return_value = user.id
        user_reader.get_hashed_password.return_value = "hashed"
        password_hasher.verify.return_value = False
        with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
            await service.login("test@example.com", "wrong")

    async def test_inactive_user(
        self,
        service: AuthService,
        user_reader: AsyncMock,
    ) -> None:
        user = _user_view(is_active=False)
        user_reader.get_user_id_by_email.return_value = user.id
        user_reader.get_hashed_password.return_value = "hashed"
        user_reader.is_user_active.return_value = False
        with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
            await service.login("test@example.com", "password")

    async def test_success(
        self,
        service: AuthService,
        user_reader: AsyncMock,
        refresh_writer: AsyncMock,
        jwt_handler: MagicMock,
    ) -> None:
        user = _user_view()
        user_reader.get_user_id_by_email.return_value = user.id
        user_reader.get_hashed_password.return_value = "hashed"
        user_reader.is_user_active.return_value = True
        user_reader.is_superuser.return_value = False

        result = await service.login("test@example.com", "password")

        assert result["access_token"] == "access-token-123"
        assert result["refresh_token"] == "refresh-token-456"
        assert result["token_type"] == "bearer"
        jwt_handler.encode_access_token.assert_called_once_with(
            str(user.id), "test@example.com", False
        )
        jwt_handler.encode_refresh_token.assert_called_once_with(str(user.id))
        refresh_writer.create.assert_called_once()
        refresh_writer.delete_expired_by_user.assert_called_once_with(user.id)


class TestRefreshAccessToken:
    async def test_invalid_token(
        self,
        service: AuthService,
        refresh_reader: AsyncMock,
    ) -> None:
        refresh_reader.get_by_hash.return_value = None
        with pytest.raises(TokenExpiredError, match="Invalid or expired refresh token"):
            await service.refresh_access_token("invalid-hash")

    async def test_inactive_user(
        self,
        service: AuthService,
        refresh_reader: AsyncMock,
        user_reader: AsyncMock,
    ) -> None:
        user_id = uuid4()
        refresh_reader.get_by_hash.return_value = user_id
        user_reader.is_user_active.return_value = False
        with pytest.raises(InvalidCredentialsError, match="User is inactive"):
            await service.refresh_access_token("valid-hash")

    async def test_user_not_found(
        self,
        service: AuthService,
        refresh_reader: AsyncMock,
        user_reader: AsyncMock,
    ) -> None:
        user_id = uuid4()
        refresh_reader.get_by_hash.return_value = user_id
        user_reader.is_user_active.return_value = True
        user_reader.get_user.return_value = None
        with pytest.raises(TokenExpiredError, match="User not found"):
            await service.refresh_access_token("valid-hash")

    async def test_success(
        self,
        service: AuthService,
        refresh_reader: AsyncMock,
        refresh_writer: AsyncMock,
        user_reader: AsyncMock,
        jwt_handler: MagicMock,
    ) -> None:
        user = _user_view()
        refresh_reader.get_by_hash.return_value = user.id
        user_reader.is_user_active.return_value = True
        user_reader.get_user.return_value = user

        result = await service.refresh_access_token("old-hash")

        assert result["access_token"] == "access-token-123"
        assert result["refresh_token"] == "refresh-token-456"
        refresh_writer.delete.assert_called_once_with("old-hash")
        refresh_writer.create.assert_called_once()


class TestLogout:
    async def test_deletes_refresh_token(
        self,
        service: AuthService,
        refresh_writer: AsyncMock,
    ) -> None:
        await service.logout("token-hash")
        refresh_writer.delete.assert_called_once_with("token-hash")


class TestGetCurrentUser:
    async def test_user_not_found(
        self,
        service: AuthService,
        user_reader: AsyncMock,
    ) -> None:
        user_reader.get_user.return_value = None
        with pytest.raises(InvalidCredentialsError, match="User not found"):
            await service.get_current_user(uuid4())

    async def test_inactive_user(
        self,
        service: AuthService,
        user_reader: AsyncMock,
    ) -> None:
        user_reader.get_user.return_value = _user_view(is_active=False)
        with pytest.raises(InvalidCredentialsError, match="User is inactive"):
            await service.get_current_user(uuid4())

    async def test_success(
        self,
        service: AuthService,
        user_reader: AsyncMock,
    ) -> None:
        user = _user_view()
        user_reader.get_user.return_value = user
        result = await service.get_current_user(user.id)
        assert result == user
