"""Tests for split audit application services."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dto.audit import AuditLogPageDTO
from app.application.services.audit_event_service import AuditEventService
from app.application.services.audit_log_service import AuditLogService
from app.core.exceptions import AuditWriteError


async def test_event_service_sanitizes_optional_payload() -> None:
    optional, required = AsyncMock(), AsyncMock()
    service = AuditEventService(optional, required)

    await service.log(
        "execute",
        node_id=uuid4(),
        details={"command": "secret", "result": "ok"},
    )

    event = optional.enqueue.call_args.args[0]
    assert event.details == {"result": "ok"}


async def test_required_event_uses_independent_outbox() -> None:
    optional, required = AsyncMock(), AsyncMock()
    service = AuditEventService(optional, required)

    await service.log_required("execute", details={"result": "started"})

    required.enqueue.assert_awaited_once()
    optional.enqueue.assert_not_awaited()


async def test_event_failures_use_domain_error() -> None:
    optional, required = AsyncMock(), AsyncMock()
    optional.enqueue.side_effect = RuntimeError("db")

    with pytest.raises(AuditWriteError):
        await AuditEventService(optional, required).log("execute")


async def test_log_service_builds_query_and_delegates_cleanup() -> None:
    reader, writer = AsyncMock(), AsyncMock()
    reader.list_logs.return_value = AuditLogPageDTO(items=(), total=0)
    writer.delete_before.return_value = 3
    service = AuditLogService(reader, writer)

    page = await service.get_logs(page=2, size=10)
    deleted = await service.cleanup_old_logs(30)

    assert page.total == 0
    query = reader.list_logs.call_args.args[0]
    assert (query.offset, query.limit) == (10, 10)
    assert deleted == 3
