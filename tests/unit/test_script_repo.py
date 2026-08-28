"""Unit tests for ScriptRepository with in-memory SQLite."""

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

from app.adapters.persistence.dao.script import ScriptRepository
from app.models.base import Base
from app.models.node import NodeModel  # noqa: F401
from app.models.script import ScriptModel  # noqa: F401
from app.models.script_execution import ScriptExecutionModel  # noqa: F401


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
def repo(session: AsyncSession) -> ScriptRepository:
    return ScriptRepository(session)


def _default_steps() -> list[dict[str, object]]:
    return [
        {
            "label": "Check disk",
            "type": "inline",
            "command": "df -h",
            "on_failure": "stop",
        }
    ]


def _script_data(**overrides: object) -> dict[str, object]:
    defaults = {
        "name": "deploy_check",
        "description": "Pre-deploy check",
        "steps": _default_steps(),
    }
    defaults.update(overrides)
    return defaults


async def test_get_by_id_found(repo: ScriptRepository) -> None:
    script = await repo.create(_script_data())
    result = await repo.get_by_id(script.id)
    assert result is not None
    assert result.name == "deploy_check"


async def test_get_by_id_not_found(repo: ScriptRepository) -> None:
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


async def test_get_all_empty(repo: ScriptRepository) -> None:
    result = await repo.get_all()
    assert result == []


async def test_get_all_with_data(repo: ScriptRepository) -> None:
    await repo.create(_script_data(name="s1"))
    await repo.create(_script_data(name="s2"))
    scripts = await repo.get_all()
    assert len(scripts) == 2


async def test_get_all_pagination(repo: ScriptRepository) -> None:
    for i in range(5):
        await repo.create(_script_data(name=f"script-{i}"))
    scripts = await repo.get_all(skip=2, limit=2)
    assert len(scripts) == 2


async def test_create(repo: ScriptRepository) -> None:
    script = await repo.create(_script_data())
    assert script.id is not None
    assert script.name == "deploy_check"
    assert len(script.steps) == 1
    assert script.steps[0]["label"] == "Check disk"


async def test_create_with_multiple_steps(repo: ScriptRepository) -> None:
    steps = [
        {
            "label": "Step 1",
            "type": "inline",
            "command": "echo 1",
            "on_failure": "stop",
        },
        {
            "label": "Step 2",
            "type": "inline",
            "command": "echo 2",
            "on_failure": "continue",
        },
    ]
    script = await repo.create(_script_data(steps=steps))
    assert len(script.steps) == 2


async def test_update_found(repo: ScriptRepository) -> None:
    script = await repo.create(_script_data())
    updated = await repo.update(script.id, {"name": "updated_script"})
    assert updated is not None
    assert updated.name == "updated_script"


async def test_update_not_found(repo: ScriptRepository) -> None:
    result = await repo.update(uuid.uuid4(), {"name": "x"})
    assert result is None


async def test_delete_found(repo: ScriptRepository) -> None:
    script = await repo.create(_script_data())
    result = await repo.delete(script.id)
    assert result is True
    assert await repo.get_by_id(script.id) is None


async def test_delete_not_found(repo: ScriptRepository) -> None:
    result = await repo.delete(uuid.uuid4())
    assert result is False


async def test_count_empty(repo: ScriptRepository) -> None:
    count = await repo.count()
    assert count == 0


async def test_count_with_data(repo: ScriptRepository) -> None:
    await repo.create(_script_data(name="s1"))
    await repo.create(_script_data(name="s2"))
    await repo.create(_script_data(name="s3"))
    count = await repo.count()
    assert count == 3


async def test_count_after_delete(repo: ScriptRepository) -> None:
    script = await repo.create(_script_data())
    assert await repo.count() == 1
    await repo.delete(script.id)
    assert await repo.count() == 0
