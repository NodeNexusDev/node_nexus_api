"""Unit tests for ScriptExecutionRepository with in-memory SQLite."""

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
from app.models.node import NodeModel  # noqa: F401
from app.models.script import ScriptModel  # noqa: F401
from app.models.script_execution import ScriptExecutionModel  # noqa: F401
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository


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
def script_repo(session: AsyncSession) -> ScriptRepository:
    return ScriptRepository(session)


@pytest.fixture
def repo(session: AsyncSession) -> ScriptExecutionRepository:
    return ScriptExecutionRepository(session)


async def _create_script(
    script_repo: ScriptRepository, name: str | None = None
) -> uuid.UUID:
    steps = [
        {
            "label": "Step 1",
            "type": "inline",
            "command": "echo ok",
            "on_failure": "stop",
        }
    ]
    script = await script_repo.create(
        {
            "name": name or f"test_script_{uuid.uuid4().hex[:8]}",
            "steps": steps,
        }
    )
    return script.id


async def test_create(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    node_id = uuid.uuid4()
    execution = await repo.create(
        {
            "script_id": script_id,
            "node_id": node_id,
            "status": "running",
            "params": {"key": "value"},
            "steps": [],
        }
    )
    assert execution.id is not None
    assert execution.status == "running"
    assert execution.script_id == script_id
    assert execution.node_id == node_id


async def test_get_by_id_found(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    execution = await repo.create(
        {
            "script_id": script_id,
            "status": "completed",
        }
    )
    result = await repo.get_by_id(execution.id)
    assert result is not None
    assert result.status == "completed"


async def test_get_by_id_not_found(repo: ScriptExecutionRepository) -> None:
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


async def test_get_by_script_id_empty(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    result = await repo.get_by_script_id(script_id)
    assert result == []


async def test_get_by_script_id_with_data(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    node1 = uuid.uuid4()
    node2 = uuid.uuid4()
    await repo.create({"script_id": script_id, "node_id": node1, "status": "completed"})
    await repo.create({"script_id": script_id, "node_id": node1, "status": "failed"})
    await repo.create({"script_id": script_id, "node_id": node2, "status": "completed"})

    results = await repo.get_by_script_id(script_id)
    assert len(results) == 3


async def test_get_by_script_id_pagination(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    for _ in range(5):
        await repo.create({"script_id": script_id, "status": "completed"})

    results = await repo.get_by_script_id(script_id, skip=1, limit=2)
    assert len(results) == 2


async def test_get_by_script_id_ordered_by_started_at_desc(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    e1 = await repo.create({"script_id": script_id, "status": "completed"})
    e2 = await repo.create({"script_id": script_id, "status": "completed"})

    results = await repo.get_by_script_id(script_id)
    assert results[0].id == e2.id
    assert results[1].id == e1.id


async def test_count_by_script_id(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    other_script_id = await _create_script(script_repo)
    await repo.create({"script_id": script_id, "status": "completed"})
    await repo.create({"script_id": script_id, "status": "failed"})
    await repo.create({"script_id": other_script_id, "status": "completed"})

    count = await repo.count_by_script_id(script_id)
    assert count == 2


async def test_update(
    repo: ScriptExecutionRepository, script_repo: ScriptRepository
) -> None:
    script_id = await _create_script(script_repo)
    execution = await repo.create({"script_id": script_id, "status": "running"})
    updated = await repo.update(
        execution.id,
        {
            "status": "completed",
            "steps": [{"step_index": 0, "exit_code": 0}],
        },
    )
    assert updated is not None
    assert updated.status == "completed"


async def test_update_not_found(repo: ScriptExecutionRepository) -> None:
    result = await repo.update(uuid.uuid4(), {"status": "completed"})
    assert result is None
