"""Persistence tests for script schedules."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.script import ScriptModel
from app.models.script_schedule import ScriptScheduleModel
from app.repositories.script_schedule_repo import ScriptScheduleRepository


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                ScriptModel.__table__,
                ScriptScheduleModel.__table__,
            ],
        )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest.fixture
def repository(session: AsyncSession) -> ScriptScheduleRepository:
    return ScriptScheduleRepository(session)


def schedule_data() -> dict:
    return {
        "cron": "0 9 * * *",
        "timezone": "UTC",
        "node_ids": [],
        "params": {},
        "enabled": True,
        "misfire_grace_seconds": 60,
    }


async def test_upsert_create_update_and_list(
    repository: ScriptScheduleRepository,
) -> None:
    script_id = uuid4()
    created = await repository.upsert(script_id, schedule_data())
    assert created.script_id == script_id

    updated = await repository.upsert(
        script_id, {**schedule_data(), "cron": "0 18 * * *"}
    )
    assert updated.id == created.id
    assert updated.cron == "0 18 * * *"
    assert await repository.get_by_script_id(script_id) is updated
    assert await repository.list_enabled() == [updated]


async def test_get_and_delete_missing(
    repository: ScriptScheduleRepository,
) -> None:
    script_id = uuid4()
    assert await repository.get_by_script_id(script_id) is None
    assert await repository.delete_by_script_id(script_id) is False


async def test_delete_existing(repository: ScriptScheduleRepository) -> None:
    script_id = uuid4()
    await repository.upsert(script_id, schedule_data())
    assert await repository.delete_by_script_id(script_id) is True
    assert await repository.get_by_script_id(script_id) is None
