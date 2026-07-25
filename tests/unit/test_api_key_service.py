"""Unit tests for APIKeyService."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import APIKeyNotFoundError, APIKeyRevokedError
from app.models.api_key import APIKeyModel
from app.repositories.api_key_repo import APIKeyRepository
from app.services.api_key_service import APIKeyService, generate_api_key


def _make_api_key_model(**overrides: Any) -> APIKeyModel:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "test-key",
        "key_hash": "abc123",
        "key_prefix": "nnk_abcd",
        "is_active": True,
        "created_at": datetime.now(UTC),
        "last_used_at": None,
    }
    defaults.update(overrides)
    return APIKeyModel(**defaults)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=APIKeyRepository)


@pytest.fixture
def service(repo: AsyncMock) -> APIKeyService:
    return APIKeyService(repository=repo)


# --- generate_api_key ---


class TestGenerateApiKey:
    def test_format(self) -> None:
        plain_key, key_hash, key_prefix = generate_api_key()
        assert plain_key.startswith("nnk_")
        assert len(plain_key) == 52  # nnk_ (4) + 48 random chars
        assert len(key_hash) == 64  # SHA-256 hex digest
        assert key_prefix == plain_key[:8]

    def test_unique(self) -> None:
        key1, _, _ = generate_api_key()
        key2, _, _ = generate_api_key()
        assert key1 != key2

    def test_hash_consistent(self) -> None:
        import hashlib

        plain_key, key_hash, _ = generate_api_key()
        expected = hashlib.sha256(plain_key.encode()).hexdigest()
        assert key_hash == expected


# --- create_api_key ---


class TestCreateApiKey:
    async def test_success(self, service: APIKeyService, repo: AsyncMock) -> None:
        # Use side_effect to capture what the service passes
        async def fake_create(**kwargs: Any) -> APIKeyModel:
            return _make_api_key_model(
                name=kwargs["name"],
                key_hash=kwargs["key_hash"],
                key_prefix=kwargs["key_prefix"],
            )

        repo.create.side_effect = fake_create
        result = await service.create_api_key("my-key")
        assert result.name == "my-key"
        assert result.key.startswith("nnk_")
        assert len(result.key) == 52

    async def test_repo_called(self, service: APIKeyService, repo: AsyncMock) -> None:
        async def fake_create(**kwargs: Any) -> APIKeyModel:
            return _make_api_key_model(
                name=kwargs["name"],
                key_hash=kwargs["key_hash"],
                key_prefix=kwargs["key_prefix"],
            )

        repo.create.side_effect = fake_create
        await service.create_api_key("my-key")
        repo.create.assert_called_once()
        call_kwargs = repo.create.call_args[1]
        assert call_kwargs["name"] == "my-key"
        assert len(call_kwargs["key_hash"]) == 64
        assert call_kwargs["key_prefix"].startswith("nnk_")


# --- validate_api_key ---


class TestValidateApiKey:
    async def test_valid(self, service: APIKeyService, repo: AsyncMock) -> None:
        orm_model = _make_api_key_model()
        repo.get_by_key_hash.return_value = orm_model
        await service.validate_api_key("nnk_validkey123")
        repo.update_last_used.assert_called_once_with(orm_model.id)

    async def test_invalid(self, service: APIKeyService, repo: AsyncMock) -> None:
        repo.get_by_key_hash.return_value = None
        with pytest.raises(APIKeyNotFoundError):
            await service.validate_api_key("nnk_unknown")

    async def test_revoked(self, service: APIKeyService, repo: AsyncMock) -> None:
        orm_model = _make_api_key_model(is_active=False)
        repo.get_by_key_hash.return_value = orm_model
        with pytest.raises(APIKeyRevokedError):
            await service.validate_api_key("nnk_revokedkey")


# --- revoke_api_key ---


class TestRevokeApiKey:
    async def test_success(self, service: APIKeyService, repo: AsyncMock) -> None:
        orm_model = _make_api_key_model()
        repo.get_by_id.return_value = orm_model
        await service.revoke_api_key(orm_model.id)
        repo.revoke.assert_called_once_with(orm_model.id)

    async def test_not_found(self, service: APIKeyService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(APIKeyNotFoundError):
            await service.revoke_api_key(uuid.uuid4())


# --- list_api_keys ---


class TestListApiKeys:
    async def test_pagination(self, service: APIKeyService, repo: AsyncMock) -> None:
        repo.list_all.return_value = ([], 0)
        result = await service.list_api_keys(page=2, size=10)
        assert result.total == 0
        assert result.items == []
        repo.list_all.assert_called_once_with(offset=10, limit=10)
