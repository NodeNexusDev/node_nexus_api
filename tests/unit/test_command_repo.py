"""Unit tests for CommandRepository with in-memory SQLite."""

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

from app.adapters.persistence.dao.command import CommandRepository
from app.models.base import Base
from app.models.command import CommandModel  # noqa: F401
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
def repo(session: AsyncSession) -> CommandRepository:
    return CommandRepository(session)


def _command_data(**overrides) -> dict:
    defaults = {
        "name": "check_disk",
        "command": "df -h",
        "description": "Check disk usage",
    }
    defaults.update(overrides)
    return defaults


async def test_get_by_id_found(repo: CommandRepository) -> None:
    cmd = await repo.create(_command_data())
    result = await repo.get_by_id(cmd.id)
    assert result is not None
    assert result.name == "check_disk"


async def test_get_by_id_not_found(repo: CommandRepository) -> None:
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


async def test_get_all_empty(repo: CommandRepository) -> None:
    result = await repo.get_all()
    assert result == []


async def test_get_all_with_data(repo: CommandRepository) -> None:
    await repo.create(_command_data(name="cmd1"))
    await repo.create(_command_data(name="cmd2"))
    cmds = await repo.get_all()
    assert len(cmds) == 2


async def test_get_all_pagination(repo: CommandRepository) -> None:
    for i in range(5):
        await repo.create(_command_data(name=f"cmd-{i}"))
    cmds = await repo.get_all(skip=2, limit=2)
    assert len(cmds) == 2


async def test_create(repo: CommandRepository) -> None:
    cmd = await repo.create(_command_data())
    assert cmd.id is not None
    assert cmd.name == "check_disk"
    assert cmd.command == "df -h"


async def test_create_with_parameters(repo: CommandRepository) -> None:
    params = [{"name": "service", "type": "string", "required": True}]
    cmd = await repo.create(_command_data(parameters=params))
    assert cmd.parameters == params


async def test_update_found(repo: CommandRepository) -> None:
    cmd = await repo.create(_command_data())
    updated = await repo.update(cmd.id, {"name": "updated_cmd"})
    assert updated is not None
    assert updated.name == "updated_cmd"


async def test_update_not_found(repo: CommandRepository) -> None:
    result = await repo.update(uuid.uuid4(), {"name": "x"})
    assert result is None


async def test_delete_found(repo: CommandRepository) -> None:
    cmd = await repo.create(_command_data())
    result = await repo.delete(cmd.id)
    assert result is True
    assert await repo.get_by_id(cmd.id) is None


async def test_delete_not_found(repo: CommandRepository) -> None:
    result = await repo.delete(uuid.uuid4())
    assert result is False


async def test_count_empty(repo: CommandRepository) -> None:
    count = await repo.count()
    assert count == 0


async def test_count_with_data(repo: CommandRepository) -> None:
    await repo.create(_command_data(name="c1"))
    await repo.create(_command_data(name="c2"))
    await repo.create(_command_data(name="c3"))
    count = await repo.count()
    assert count == 3


async def test_count_after_delete(repo: CommandRepository) -> None:
    cmd = await repo.create(_command_data())
    assert await repo.count() == 1
    await repo.delete(cmd.id)
    assert await repo.count() == 0
