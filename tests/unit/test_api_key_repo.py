"""Unit tests for APIKeyRepository with in-memory SQLite."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.repositories.api_key_repo import APIKeyRepository


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(
    engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        async with s.begin():
            yield s


@pytest.fixture
def repo(session: AsyncSession) -> APIKeyRepository:
    return APIKeyRepository(session)


# --- create ---


async def test_create(repo: APIKeyRepository) -> None:
    model = await repo.create(
        name="test-key",
        key_hash="abc123def456",
        key_prefix="nnk_abcd",
    )
    assert model.name == "test-key"
    assert model.key_hash == "abc123def456"
    assert model.key_prefix == "nnk_abcd"
    assert model.is_active is True
    assert model.id is not None


# --- get_by_key_hash ---


async def test_get_by_key_hash_found(repo: APIKeyRepository) -> None:
    await repo.create(name="k1", key_hash="hash1", key_prefix="nnk_aaaa")
    result = await repo.get_by_key_hash("hash1")
    assert result is not None
    assert result.name == "k1"


async def test_get_by_key_hash_not_found(repo: APIKeyRepository) -> None:
    result = await repo.get_by_key_hash("nonexistent")
    assert result is None


# --- list_all ---


async def test_list_all(repo: APIKeyRepository) -> None:
    await repo.create(name="k1", key_hash="h1", key_prefix="nnk_1111")
    await repo.create(name="k2", key_hash="h2", key_prefix="nnk_2222")
    items, total = await repo.list_all(offset=0, limit=10)
    assert total == 2
    assert len(items) == 2


async def test_list_all_pagination(repo: APIKeyRepository) -> None:
    for i in range(5):
        await repo.create(name=f"k{i}", key_hash=f"h{i}", key_prefix=f"nnk_{i:04d}")
    items, total = await repo.list_all(offset=2, limit=2)
    assert total == 5
    assert len(items) == 2


# --- revoke ---


async def test_revoke(repo: APIKeyRepository) -> None:
    model = await repo.create(name="k1", key_hash="h1", key_prefix="nnk_1111")
    assert model.is_active is True
    await repo.revoke(model.id)
    refreshed = await repo.get_by_key_hash("h1")
    assert refreshed is not None
    assert refreshed.is_active is False


# --- update_last_used ---


async def test_update_last_used(repo: APIKeyRepository) -> None:
    model = await repo.create(name="k1", key_hash="h1", key_prefix="nnk_1111")
    assert model.last_used_at is None
    await repo.update_last_used(model.id)
    refreshed = await repo.get_by_key_hash("h1")
    assert refreshed is not None
    assert refreshed.last_used_at is not None
