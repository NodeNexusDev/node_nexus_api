"""Unit tests for API key enhancements: PATCH, expiry, scope."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import (
    APIKeyExpiredError,
    APIKeyNotFoundError,
    APIKeyRevokedError,
)
from app.schemas.api_key import APIKeyResponse, APIKeyUpdate
from app.services.api_key_service import APIKeyService


def _make_api_key_response(**overrides: Any) -> APIKeyResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-key",
        "key_prefix": "nnk_abcd",
        "is_active": True,
        "scope": "read-write",
        "created_at": datetime.now(UTC),
        "last_used_at": None,
        "expires_at": None,
    }
    defaults.update(overrides)
    return APIKeyResponse(**defaults)


# --- APIKeyUpdate schema tests ---


class TestApiKeyUpdateSchema:
    def test_update_name_only(self) -> None:
        update = APIKeyUpdate(name="new-name")
        data = update.model_dump(exclude_unset=True)
        assert data == {"name": "new-name"}

    def test_update_is_active_only(self) -> None:
        update = APIKeyUpdate(is_active=False)
        data = update.model_dump(exclude_unset=True)
        assert data == {"is_active": False}

    def test_update_scope_only(self) -> None:
        update = APIKeyUpdate(scope="read-only")
        data = update.model_dump(exclude_unset=True)
        assert data == {"scope": "read-only"}

    def test_update_expires_at(self) -> None:
        expires = datetime.now(UTC) + timedelta(days=30)
        update = APIKeyUpdate(expires_at=expires)
        data = update.model_dump(exclude_unset=True)
        assert "expires_at" in data

    def test_update_multiple_fields(self) -> None:
        update = APIKeyUpdate(name="new", is_active=False, scope="read-only")
        data = update.model_dump(exclude_unset=True)
        assert len(data) == 3

    def test_update_empty(self) -> None:
        update = APIKeyUpdate()
        data = update.model_dump(exclude_unset=True)
        assert data == {}


# --- APIKeyResponse schema tests ---


class TestApiKeyResponseSchema:
    def test_response_with_scope(self) -> None:
        resp = _make_api_key_response(scope="read-only")
        assert resp.scope == "read-only"

    def test_response_with_expires_at(self) -> None:
        expires = datetime.now(UTC) + timedelta(days=30)
        resp = _make_api_key_response(expires_at=expires)
        assert resp.expires_at == expires

    def test_response_without_expires_at(self) -> None:
        resp = _make_api_key_response(expires_at=None)
        assert resp.expires_at is None


# --- APIKeyService update tests ---


class TestApiKeyServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_api_key_name(self) -> None:
        mock_repo = AsyncMock()
        key_id = uuid.uuid4()
        updated_model = type(
            "Model",
            (),
            {
                "id": key_id,
                "name": "new-name",
                "key_prefix": "nnk_abcd",
                "is_active": True,
                "scope": "read-write",
                "created_at": datetime.now(UTC),
                "last_used_at": None,
                "expires_at": None,
            },
        )()
        mock_repo.get_by_id.return_value = updated_model
        mock_repo.update.return_value = updated_model

        service = APIKeyService(repository=mock_repo)
        result = await service.update_api_key(key_id, APIKeyUpdate(name="new-name"))

        assert result.name == "new-name"
        mock_repo.update.assert_called_once_with(key_id, {"name": "new-name"})

    @pytest.mark.asyncio
    async def test_update_api_key_not_found(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None

        service = APIKeyService(repository=mock_repo)
        with pytest.raises(APIKeyNotFoundError):
            await service.update_api_key(uuid.uuid4(), APIKeyUpdate(name="new"))


# --- APIKeyService expiry check tests ---


class TestApiKeyServiceExpiry:
    @pytest.mark.asyncio
    async def test_validate_expired_key(self) -> None:
        mock_repo = AsyncMock()
        expired_model = type(
            "Model",
            (),
            {
                "id": uuid.uuid4(),
                "is_active": True,
                "expires_at": datetime.now(UTC) - timedelta(days=1),
            },
        )()
        mock_repo.get_by_key_hash.return_value = expired_model

        service = APIKeyService(repository=mock_repo)
        with pytest.raises(APIKeyExpiredError):
            await service.validate_api_key("nnk_expired_key")

    @pytest.mark.asyncio
    async def test_validate_valid_key(self) -> None:
        mock_repo = AsyncMock()
        valid_model = type(
            "Model",
            (),
            {
                "id": uuid.uuid4(),
                "is_active": True,
                "expires_at": datetime.now(UTC) + timedelta(days=30),
            },
        )()
        mock_repo.get_by_key_hash.return_value = valid_model

        service = APIKeyService(repository=mock_repo)
        # Should not raise
        await service.validate_api_key("nnk_valid_key")
        mock_repo.update_last_used.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_key_no_expiry(self) -> None:
        mock_repo = AsyncMock()
        model = type(
            "Model",
            (),
            {
                "id": uuid.uuid4(),
                "is_active": True,
                "expires_at": None,
            },
        )()
        mock_repo.get_by_key_hash.return_value = model

        service = APIKeyService(repository=mock_repo)
        # Should not raise (no expiry set)
        await service.validate_api_key("nnk_no_expiry_key")

    @pytest.mark.asyncio
    async def test_validate_revoked_key(self) -> None:
        mock_repo = AsyncMock()
        revoked_model = type(
            "Model",
            (),
            {
                "id": uuid.uuid4(),
                "is_active": False,
                "expires_at": None,
            },
        )()
        mock_repo.get_by_key_hash.return_value = revoked_model

        service = APIKeyService(repository=mock_repo)
        with pytest.raises(APIKeyRevokedError):
            await service.validate_api_key("nnk_revoked_key")


# --- APIKeyService scope tests ---


class TestApiKeyServiceScope:
    @pytest.mark.asyncio
    async def test_get_scope_read_write(self) -> None:
        mock_repo = AsyncMock()
        model = type(
            "Model",
            (),
            {"scope": "read-write"},
        )()
        mock_repo.get_by_key_hash.return_value = model

        service = APIKeyService(repository=mock_repo)
        scope = await service.get_api_key_scope("nnk_key")
        assert scope == "read-write"

    @pytest.mark.asyncio
    async def test_get_scope_read_only(self) -> None:
        mock_repo = AsyncMock()
        model = type(
            "Model",
            (),
            {"scope": "read-only"},
        )()
        mock_repo.get_by_key_hash.return_value = model

        service = APIKeyService(repository=mock_repo)
        scope = await service.get_api_key_scope("nnk_key")
        assert scope == "read-only"

    @pytest.mark.asyncio
    async def test_get_scope_not_found(self) -> None:
        mock_repo = AsyncMock()
        mock_repo.get_by_key_hash.return_value = None

        service = APIKeyService(repository=mock_repo)
        with pytest.raises(APIKeyNotFoundError):
            await service.get_api_key_scope("nnk_invalid")
