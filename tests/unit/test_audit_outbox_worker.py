"""Unit tests for the SQLAlchemy audit-outbox worker lifecycle."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker
from app.models.audit_log import AuditLogModel
from app.models.audit_outbox import AuditOutboxModel
from app.models.node import NodeModel
from tests.typing import as_typed


async def test_worker_lifecycle_and_background_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = AuditOutboxWorker(MagicMock())
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
    monkeypatch.setattr(
        "app.adapters.persistence.audit_outbox_worker.asyncio.sleep",
        AsyncMock(),
    )
    with pytest.raises(asyncio.CancelledError):
        await worker._run()


def _session() -> MagicMock:
    session = MagicMock()
    transaction = AsyncMock()
    transaction.__aenter__.return_value = None
    transaction.__aexit__.return_value = False
    session.begin_nested.return_value = transaction
    session.get = AsyncMock()
    session.flush = AsyncMock()
    return session


def _event(*, attempts: int = 0) -> AuditOutboxModel:
    return AuditOutboxModel(
        id=uuid4(),
        payload={
            "node_id": None,
            "action": "node.command.requested",
            "user": None,
            "details": None,
        },
        attempts=attempts,
        status="pending",
        next_attempt_at=datetime.now(UTC),
        last_error_type=None,
        delivered_at=None,
    )


class _SessionContext:
    def __init__(self, session: MagicMock) -> None:
        self._session = session

    async def __aenter__(self) -> MagicMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


class _Sessionmaker:
    def __init__(self, session: MagicMock) -> None:
        self._session = session

    def __call__(self) -> _SessionContext:
        return _SessionContext(self._session)


async def test_delivery_is_idempotent_when_audit_row_already_exists() -> None:
    session = _session()
    session.get.return_value = object()
    event = _event()
    now = datetime.now(UTC)

    delivered = await AuditOutboxWorker(MagicMock())._deliver(session, event, now)

    assert delivered is True
    assert event.status == "completed"
    assert event.delivered_at == now
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


async def test_temporary_delivery_failure_schedules_exponential_retry() -> None:
    session = _session()
    session.get.side_effect = RuntimeError("database unavailable")
    event = _event()
    now = datetime.now(UTC)

    delivered = await AuditOutboxWorker(
        MagicMock(),
        max_attempts=3,
    )._deliver(session, event, now)

    assert delivered is False
    assert event.attempts == 1
    assert event.status == "pending"
    assert event.last_error_type == "RuntimeError"
    assert event.next_attempt_at == now + timedelta(seconds=1)


async def test_delivery_failure_stops_after_max_attempts() -> None:
    session = _session()
    session.get.side_effect = RuntimeError("invalid payload")
    event = _event(attempts=1)

    delivered = await AuditOutboxWorker(
        MagicMock(),
        max_attempts=2,
    )._deliver(session, event, datetime.now(UTC))

    assert delivered is False
    assert event.attempts == 2
    assert event.status == "failed"
    assert event.last_error_type == "RuntimeError"


async def test_run_once_delivers_due_batch_and_updates_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    transaction = AsyncMock()
    transaction.__aenter__.return_value = None
    transaction.__aexit__.return_value = False
    session.begin.return_value = transaction
    events = [_event(), _event()]
    result = MagicMock()
    result.scalars.return_value = events
    session.execute = AsyncMock(return_value=result)
    worker = AuditOutboxWorker(as_typed(_Sessionmaker(session)))
    deliver = AsyncMock(side_effect=[True, False])
    update_metrics = AsyncMock()
    monkeypatch.setattr(worker, "_deliver", deliver)
    monkeypatch.setattr(worker, "_update_metrics", update_metrics)

    delivered = await worker.run_once()

    assert delivered == 1
    assert deliver.await_count == 2
    update_metrics.assert_awaited_once()


async def test_successful_delivery_creates_missing_audit_row() -> None:
    session = _session()
    session.get.return_value = None
    event = _event(attempts=1)
    now = datetime.now(UTC)

    delivered = await AuditOutboxWorker(MagicMock())._deliver(session, event, now)

    assert delivered is True
    assert event.attempts == 2
    assert event.last_error_type is None
    session.add.assert_called_once()
    assert isinstance(session.add.call_args.args[0], AuditLogModel)
    session.flush.assert_awaited_once()


async def test_audit_log_mapping_preserves_existing_node() -> None:
    session = _session()
    node_id = uuid4()
    session.get.return_value = MagicMock(spec=NodeModel)
    event_id = uuid4()

    model = await AuditOutboxWorker._to_audit_log(
        session,
        event_id,
        {
            "node_id": str(node_id),
            "action": "execute",
            "user": "operator",
            "details": '{"ok": true}',
        },
    )

    assert model.id == event_id
    assert model.node_id == node_id
    assert model.user == "operator"


async def test_audit_log_mapping_drops_deleted_node() -> None:
    session = _session()
    session.get.return_value = None

    model = await AuditOutboxWorker._to_audit_log(
        session,
        uuid4(),
        {
            "node_id": str(uuid4()),
            "action": "execute",
        },
    )

    assert model.node_id is None


async def test_metrics_handle_pending_age_and_empty_queue() -> None:
    now = datetime.now(UTC)
    session = _session()
    with_pending = MagicMock()
    with_pending.one.return_value = (3, now - timedelta(seconds=7))
    empty = MagicMock()
    empty.one.return_value = (0, None)
    session.execute = AsyncMock(side_effect=[with_pending, empty])

    await AuditOutboxWorker._update_metrics(session, now)
    await AuditOutboxWorker._update_metrics(session, now)

    assert session.execute.await_count == 2
