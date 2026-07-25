"""Integration tests for AuditLogRepository with in-memory SQLite."""

import uuid
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
from app.repositories.audit_repo import AuditLogRepository


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        async with s.begin():
            yield s


@pytest.fixture
def repo(session: AsyncSession) -> AuditLogRepository:
    return AuditLogRepository(session)


async def test_create(repo: AuditLogRepository) -> None:
    log = await repo.create(
        {"action": "create", "node_id": uuid.uuid4(), "details": '{"name": "test"}'}
    )
    assert log.id is not None
    assert log.action == "create"


async def test_get_all_empty(repo: AuditLogRepository) -> None:
    logs = await repo.get_all()
    assert logs == []


async def test_get_all_with_data(repo: AuditLogRepository) -> None:
    node_id = uuid.uuid4()
    await repo.create({"action": "create", "node_id": node_id})
    await repo.create({"action": "update", "node_id": node_id})
    await repo.create({"action": "delete", "node_id": uuid.uuid4()})

    logs = await repo.get_all(node_id=node_id)
    assert len(logs) == 2


async def test_get_all_filter_action(repo: AuditLogRepository) -> None:
    await repo.create({"action": "create"})
    await repo.create({"action": "update"})
    await repo.create({"action": "create"})

    logs = await repo.get_all(action="create")
    assert len(logs) == 2


async def test_get_all_pagination(repo: AuditLogRepository) -> None:
    for _ in range(5):
        await repo.create({"action": "test"})

    logs = await repo.get_all(skip=2, limit=2)
    assert len(logs) == 2


async def test_count_empty(repo: AuditLogRepository) -> None:
    assert await repo.count() == 0


async def test_count_with_data(repo: AuditLogRepository) -> None:
    await repo.create({"action": "a"})
    await repo.create({"action": "b"})
    assert await repo.count() == 2


async def test_count_filter_node_id(repo: AuditLogRepository) -> None:
    node_id = uuid.uuid4()
    await repo.create({"action": "a", "node_id": node_id})
    await repo.create({"action": "b", "node_id": uuid.uuid4()})
    assert await repo.count(node_id=node_id) == 1


async def test_count_filter_action(repo: AuditLogRepository) -> None:
    await repo.create({"action": "create"})
    await repo.create({"action": "update"})
    assert await repo.count(action="create") == 1
