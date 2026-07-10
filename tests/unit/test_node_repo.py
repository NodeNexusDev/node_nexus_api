"""Unit tests for NodeRepository with in-memory SQLite."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.repositories.node_repo import NodeRepository


@pytest_asyncio.fixture
async def engine() -> AsyncEngine:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncSession:
    sm = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as s:
        async with s.begin():
            yield s


@pytest.fixture
def repo(session: AsyncSession) -> NodeRepository:
    return NodeRepository(session)


def _node_data(**overrides) -> dict:
    defaults = {
        "name": "test-node",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
    }
    defaults.update(overrides)
    return defaults


@pytest.mark.asyncio
async def test_get_by_id_found(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    result = await repo.get_by_id(node.id)
    assert result is not None
    assert result.name == "test-node"


@pytest.mark.asyncio
async def test_get_by_id_not_found(repo: NodeRepository) -> None:
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_all_empty(repo: NodeRepository) -> None:
    result = await repo.get_all()
    assert result == []


@pytest.mark.asyncio
async def test_get_all_with_data(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="n1"))
    await repo.create(_node_data(name="n2"))
    nodes = await repo.get_all()
    assert len(nodes) == 2


@pytest.mark.asyncio
async def test_get_all_pagination(repo: NodeRepository) -> None:
    for i in range(5):
        await repo.create(_node_data(name=f"node-{i}"))
    nodes = await repo.get_all(skip=2, limit=2)
    assert len(nodes) == 2


@pytest.mark.asyncio
async def test_create(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    assert node.id is not None
    assert node.name == "test-node"


@pytest.mark.asyncio
async def test_update_found(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    updated = await repo.update(node.id, {"name": "updated"})
    assert updated is not None
    assert updated.name == "updated"


@pytest.mark.asyncio
async def test_update_not_found(repo: NodeRepository) -> None:
    result = await repo.update(uuid.uuid4(), {"name": "x"})
    assert result is None


@pytest.mark.asyncio
async def test_delete_found(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    result = await repo.delete(node.id)
    assert result is True
    assert await repo.get_by_id(node.id) is None


@pytest.mark.asyncio
async def test_delete_not_found(repo: NodeRepository) -> None:
    result = await repo.delete(uuid.uuid4())
    assert result is False
