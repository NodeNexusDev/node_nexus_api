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


def _make_log(**overrides) -> AuditLogResponse:
    defaults = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "action": "create",
        "user": None,
        "details": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return AuditLogResponse(**defaults)


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_log_creates_entry(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        await service.log("create", node_id=uuid.uuid4(), details={"name": "test"})
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_handles_exception(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        repo.create.side_effect = Exception("db error")
        await service.log("create")

    @pytest.mark.asyncio
    async def test_get_logs(self, service: AuditService, repo: AsyncMock) -> None:
        log = _make_log()
        repo.get_all.return_value = [log]
        repo.count.return_value = 1

        logs, total = await service.get_logs(page=1, size=20)
        assert len(logs) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_get_logs_filters_by_node_id(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        repo.get_all.return_value = []
        repo.count.return_value = 0

        await service.get_logs(node_id=node_id)
        repo.get_all.assert_called_once_with(
            node_id=node_id, action=None, skip=0, limit=20
        )

    @pytest.mark.asyncio
    async def test_get_logs_filters_by_action(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        repo.get_all.return_value = []
        repo.count.return_value = 0

        await service.get_logs(action="delete")
        repo.get_all.assert_called_once_with(
            node_id=None, action="delete", skip=0, limit=20
        )

    @pytest.mark.asyncio
    async def test_get_logs_pagination(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        repo.get_all.return_value = []
        repo.count.return_value = 10

        logs, total = await service.get_logs(page=3, size=5)
        assert total == 10
        repo.get_all.assert_called_once_with(
            node_id=None, action=None, skip=10, limit=5
        )

    @pytest.mark.asyncio
    async def test_get_logs_with_details(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        log = _make_log(details='{"name": "test"}')
        repo.get_all.return_value = [log]
        repo.count.return_value = 1

        logs, _ = await service.get_logs()
        assert logs[0].details == '{"name": "test"}'

    @pytest.mark.asyncio
    async def test_log_serializes_details_to_json(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        await service.log("create", details={"key": "value"})
        call_data = repo.create.call_args[0][0]
        assert call_data["details"] == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_log_no_details_sends_none(
        self, service: AuditService, repo: AsyncMock
    ) -> None:
        await service.log("create")
        call_data = repo.create.call_args[0][0]
        assert call_data["details"] is None
