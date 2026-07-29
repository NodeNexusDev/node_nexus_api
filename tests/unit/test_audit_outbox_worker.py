"""Unit tests for the SQLAlchemy audit-outbox worker lifecycle."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker


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


def _event(*, attempts: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
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
