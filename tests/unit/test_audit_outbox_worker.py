"""Unit tests for the SQLAlchemy audit-outbox worker lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

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
