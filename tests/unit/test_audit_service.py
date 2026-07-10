"""Unit tests for audit log service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.repositories.audit_repo import AuditLogRepository
from app.schemas.audit_log import AuditLogResponse
from app.services.audit_service import AuditService


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=AuditLogRepository)


@pytest.fixture
def service(repo: AsyncMock) -> AuditService:
    return AuditService(repository=repo)


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_log_creates_entry(self, service: AuditService, repo: AsyncMock) -> None:
        await service.log("create", node_id=uuid.uuid4(), details={"name": "test"})
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_handles_exception(self, service: AuditService, repo: AsyncMock) -> None:
        repo.create.side_effect = Exception("db error")
        # Should not raise
        await service.log("create")

    @pytest.mark.asyncio
    async def test_get_logs(self, service: AuditService, repo: AsyncMock) -> None:
        log = AuditLogResponse(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            action="create",
            user=None,
            details=None,
            created_at=datetime.now(UTC),
        )
        repo.get_all.return_value = [log]
        repo.count.return_value = 1

        logs, total = await service.get_logs(page=1, size=20)
        assert len(logs) == 1
        assert total == 1
