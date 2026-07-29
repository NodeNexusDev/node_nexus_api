"""Integration tests for AuditLogRepository with in-memory SQLite."""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_log import AuditLogModel
from app.models.audit_outbox import AuditOutboxModel
from app.models.base import Base
from app.models.node import NodeModel  # noqa: F401
from app.repositories.audit_repo import AuditLogRepository
from app.services.audit_outbox_worker import AuditOutboxWorker
from app.services.audit_service import RequiredAuditWriter


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
def repo(session: AsyncSession) -> AuditLogRepository:
    return AuditLogRepository(session)


@pytest.fixture
def worker(engine: AsyncEngine) -> AuditOutboxWorker:
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return AuditOutboxWorker(sessionmaker)


async def deliver(session: AsyncSession, worker: AuditOutboxWorker) -> None:
    await session.commit()
    await worker.run_once()


async def test_create(repo: AuditLogRepository) -> None:
    log = await repo.create(
        {"action": "create", "node_id": uuid.uuid4(), "details": '{"name": "test"}'}
    )
    assert log.id is not None
    assert log.action == "create"


async def test_get_all_empty(repo: AuditLogRepository) -> None:
    logs = await repo.get_all()
    assert logs == []


async def test_get_all_with_data(
    repo: AuditLogRepository, session: AsyncSession, worker: AuditOutboxWorker
) -> None:
    node_id = uuid.uuid4()
    session.add(
        NodeModel(
            id=node_id,
            name="audit-node",
            host="127.0.0.1",
            port=22,
            connection_type="ssh",
        )
    )
    await session.flush()
    await repo.create({"action": "create", "node_id": node_id})
    await repo.create({"action": "update", "node_id": node_id})
    await repo.create({"action": "delete", "node_id": uuid.uuid4()})
    await deliver(session, worker)

    logs = await repo.get_all(node_id=node_id)
    assert len(logs) == 2


async def test_get_all_filter_action(
    repo: AuditLogRepository, session: AsyncSession, worker: AuditOutboxWorker
) -> None:
    await repo.create({"action": "create"})
    await repo.create({"action": "update"})
    await repo.create({"action": "create"})
    await deliver(session, worker)

    logs = await repo.get_all(action="create")
    assert len(logs) == 2


async def test_get_all_pagination(
    repo: AuditLogRepository, session: AsyncSession, worker: AuditOutboxWorker
) -> None:
    for _ in range(5):
        await repo.create({"action": "test"})
    await deliver(session, worker)

    logs = await repo.get_all(skip=2, limit=2)
    assert len(logs) == 2


async def test_count_empty(repo: AuditLogRepository) -> None:
    assert await repo.count() == 0


async def test_count_with_data(
    repo: AuditLogRepository, session: AsyncSession, worker: AuditOutboxWorker
) -> None:
    await repo.create({"action": "a"})
    await repo.create({"action": "b"})
    await deliver(session, worker)
    assert await repo.count() == 2


async def test_count_filter_node_id(
    repo: AuditLogRepository, session: AsyncSession, worker: AuditOutboxWorker
) -> None:
    node_id = uuid.uuid4()
    session.add(
        NodeModel(
            id=node_id,
            name="audit-count-node",
            host="127.0.0.1",
            port=22,
            connection_type="ssh",
        )
    )
    await session.flush()
    await repo.create({"action": "a", "node_id": node_id})
    await repo.create({"action": "b", "node_id": uuid.uuid4()})
    await deliver(session, worker)
    assert await repo.count(node_id=node_id) == 1


async def test_count_filter_action(
    repo: AuditLogRepository, session: AsyncSession, worker: AuditOutboxWorker
) -> None:
    await repo.create({"action": "create"})
    await repo.create({"action": "update"})
    await deliver(session, worker)
    assert await repo.count(action="create") == 1


async def test_worker_marks_delivery_completed(
    repo: AuditLogRepository,
    session: AsyncSession,
    worker: AuditOutboxWorker,
) -> None:
    pending = await repo.create({"action": "node.created", "user": "system"})
    await deliver(session, worker)

    event = await session.get(AuditOutboxModel, pending.id)
    log = await session.get(AuditLogModel, pending.id)
    assert event is not None
    assert event.status == "completed"
    assert event.attempts == 1
    assert event.delivered_at is not None
    assert log is not None
    assert log.action == "node.created"


async def test_worker_is_idempotent_when_audit_log_exists(
    repo: AuditLogRepository,
    session: AsyncSession,
    worker: AuditOutboxWorker,
) -> None:
    pending = await repo.create({"action": "node.updated"})
    await session.commit()
    session.add(AuditLogModel(id=pending.id, action="node.updated"))
    await session.commit()

    assert await worker.run_once() == 1
    count = await session.scalar(
        select(AuditLogModel).where(AuditLogModel.id == pending.id)
    )
    assert count is not None


async def test_worker_retries_then_marks_failed(
    repo: AuditLogRepository,
    session: AsyncSession,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending = await repo.create({"action": "broken"})
    await session.commit()
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    worker = AuditOutboxWorker(sessionmaker, max_attempts=1)

    def fail_delivery(*args: object) -> AuditLogModel:
        raise ValueError("simulated delivery failure")

    monkeypatch.setattr(worker, "_to_audit_log", fail_delivery)
    assert await worker.run_once() == 0

    session.expire_all()
    event = await session.get(AuditOutboxModel, pending.id)
    assert event is not None
    assert event.status == "failed"
    assert event.attempts == 1
    assert event.last_error_type == "ValueError"


async def test_worker_lifecycle_and_background_error(
    worker: AuditOutboxWorker, monkeypatch: pytest.MonkeyPatch
) -> None:
    worker.start()
    worker.start()
    assert worker._task is not None
    await worker.stop()
    assert worker._task is None
    await worker.stop()

    monkeypatch.setattr(
        worker,
        "run_once",
        AsyncMock(side_effect=[RuntimeError("temporary"), asyncio.CancelledError()]),
    )
    monkeypatch.setattr("app.services.audit_outbox_worker.asyncio.sleep", AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        await worker._run()


async def test_required_writer_uses_independent_transaction(
    engine: AsyncEngine,
) -> None:
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    writer = RequiredAuditWriter(sessionmaker)
    await writer.write(
        {
            "action": "execute.requested",
            "node_id": None,
            "user": None,
            "details": None,
        }
    )
    async with sessionmaker() as session:
        event = await session.scalar(select(AuditOutboxModel))
    assert event is not None
    assert event.status == "pending"
