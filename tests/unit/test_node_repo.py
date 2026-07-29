"""Unit tests for NodeRepository with in-memory SQLite."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

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


async def test_get_by_id_found(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    result = await repo.get_by_id(node.id)
    assert result is not None
    assert result.name == "test-node"


async def test_get_by_id_not_found(repo: NodeRepository) -> None:
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


async def test_get_all_empty(repo: NodeRepository) -> None:
    result = await repo.get_all()
    assert result == []


async def test_get_all_with_data(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="n1"))
    await repo.create(_node_data(name="n2"))
    nodes = await repo.get_all()
    assert len(nodes) == 2


async def test_get_all_pagination(repo: NodeRepository) -> None:
    for i in range(5):
        await repo.create(_node_data(name=f"node-{i}"))
    nodes = await repo.get_all(skip=2, limit=2)
    assert len(nodes) == 2


async def test_create(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    assert node.id is not None
    assert node.name == "test-node"


async def test_update_found(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    updated = await repo.update(node.id, {"name": "updated"})
    assert updated is not None
    assert updated.name == "updated"


async def test_update_not_found(repo: NodeRepository) -> None:
    result = await repo.update(uuid.uuid4(), {"name": "x"})
    assert result is None


async def test_delete_found(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    result = await repo.delete(node.id)
    assert result is True
    assert await repo.get_by_id(node.id) is None


async def test_delete_not_found(repo: NodeRepository) -> None:
    result = await repo.delete(uuid.uuid4())
    assert result is False


async def test_count_empty(repo: NodeRepository) -> None:
    count = await repo.count()
    assert count == 0


async def test_count_with_data(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="n1"))
    await repo.create(_node_data(name="n2"))
    await repo.create(_node_data(name="n3"))
    count = await repo.count()
    assert count == 3


async def test_count_after_delete(repo: NodeRepository) -> None:
    node = await repo.create(_node_data())
    assert await repo.count() == 1
    await repo.delete(node.id)
    assert await repo.count() == 0


# --- get_by_ids ---


async def test_get_by_ids_returns_matching(repo: NodeRepository) -> None:
    n1 = await repo.create(_node_data(name="n1"))
    n2 = await repo.create(_node_data(name="n2"))
    await repo.create(_node_data(name="n3"))
    result = await repo.get_by_ids([n1.id, n2.id])
    assert len(result) == 2
    names = {n.name for n in result}
    assert names == {"n1", "n2"}


async def test_get_by_ids_empty_list(repo: NodeRepository) -> None:
    await repo.create(_node_data())
    result = await repo.get_by_ids([])
    assert result == []


async def test_get_by_ids_no_match(repo: NodeRepository) -> None:
    await repo.create(_node_data())
    result = await repo.get_by_ids([uuid.uuid4()])
    assert result == []


async def test_connection_dto_queries(repo: NodeRepository) -> None:
    node = await repo.create(
        _node_data(name="dto", username="root", password="encrypted")
    )
    connection = await repo.get_connection(node.id)
    assert connection is not None
    assert connection.username == "root"
    assert await repo.get_connection(uuid.uuid4()) is None
    assert len(await repo.get_connections_by_ids([node.id])) == 1


async def test_connection_dtos_by_tags_delegates() -> None:
    repository = NodeRepository(AsyncMock())
    node = MagicMock()
    node.id = uuid.uuid4()
    node.name = "node"
    node.host = "host"
    node.port = 22
    node.connection_type = "ssh"
    node.username = None
    node.password = None
    node.ssh_key = None
    node.docker_host = None
    repository.get_by_tags = AsyncMock(return_value=[node])
    assert len(await repository.get_connections_by_tags(["prod"])) == 1


async def test_postgresql_tag_query_builders() -> None:
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    result = MagicMock()
    result.scalars.return_value = scalars
    result.scalar_one.return_value = 0
    result.all.return_value = [("web",), (None,), ("prod",)]
    session.execute.return_value = result
    repository = NodeRepository(session)

    assert await repository.get_by_tags(["prod", "web"]) == []
    assert await repository.count_by_tags(["prod"]) == 0
    assert await repository.get_all_tags() == ["prod", "web"]
    assert await repository.get_filtered(tags=["prod"]) == []
    assert await repository.count_filtered(tags=["prod"]) == 0


async def test_cursor_pagination_with_and_without_cursor(
    repo: NodeRepository,
) -> None:
    first = await repo.create(_node_data(name="first"))
    first.created_at = datetime.now(UTC) - timedelta(seconds=1)
    second = await repo.create(_node_data(name="second"))
    second.created_at = datetime.now(UTC)
    await repo._session.flush()

    page = await repo.get_list_cursor(limit=1)
    assert len(page) == 2
    next_page = await repo.get_list_cursor(
        cursor=(second.created_at, second.id), limit=2
    )
    assert [node.name for node in next_page] == ["first"]


# --- get_filtered / count_filtered ---


async def test_get_filtered_by_search(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="web-1", host="10.0.0.1"))
    await repo.create(_node_data(name="db-1", host="10.0.0.2"))
    await repo.create(_node_data(name="web-2", host="10.0.0.3"))
    result = await repo.get_filtered(search="web")
    assert len(result) == 2


async def test_get_filtered_by_search_host(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="node-a", host="prod.example.com"))
    await repo.create(_node_data(name="node-b", host="staging.example.com"))
    result = await repo.get_filtered(search="prod")
    assert len(result) == 1
    assert result[0].name == "node-a"


@pytest.mark.skip(reason="SQLite does not support ARRAY.contains()")
async def test_get_filtered_by_tags(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="n1", tags=["prod", "web"]))
    await repo.create(_node_data(name="n2", tags=["prod", "db"]))
    await repo.create(_node_data(name="n3", tags=["staging", "web"]))
    result = await repo.get_filtered(tags=["prod"])
    assert len(result) == 2


@pytest.mark.skip(reason="SQLite does not support ARRAY.contains()")
async def test_get_filtered_by_tags_and_search(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="web-1", tags=["prod"]))
    await repo.create(_node_data(name="web-2", tags=["staging"]))
    await repo.create(_node_data(name="db-1", tags=["prod"]))
    result = await repo.get_filtered(tags=["prod"], search="web")
    assert len(result) == 1
    assert result[0].name == "web-1"


async def test_get_filtered_empty_result(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="n1"))
    result = await repo.get_filtered(search="nonexistent")
    assert result == []


@pytest.mark.skip(reason="SQLite does not support ARRAY.contains()")
async def test_count_filtered_matches(repo: NodeRepository) -> None:
    await repo.create(_node_data(name="web-1", tags=["prod"]))
    await repo.create(_node_data(name="db-1", tags=["prod"]))
    await repo.create(_node_data(name="web-2", tags=["staging"]))
    count = await repo.count_filtered(tags=["prod"], search="web")
    assert count == 1
