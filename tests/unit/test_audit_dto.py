"""Tests for audit application contracts."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.dto.audit import AuditLogDTO, AuditLogPageDTO
from app.application.ports.audit_log import (
    AuditLogReader,
    AuditLogWriter,
    AuditOutboxPort,
)


def test_audit_log_page_uses_immutable_items() -> None:
    item = AuditLogDTO(
        id=uuid4(),
        node_id=None,
        action="execute",
        user=None,
        details=None,
        created_at=datetime.now(UTC),
    )
    page = AuditLogPageDTO(items=(item,), total=1)

    assert page.items == (item,)
    with pytest.raises(AttributeError):
        page.total = 2  # type: ignore[misc]


def test_audit_ports_are_application_contracts() -> None:
    assert AuditLogReader.__module__.startswith("app.application")
    assert AuditLogWriter.__module__.startswith("app.application")
    assert AuditOutboxPort.__module__.startswith("app.application")
