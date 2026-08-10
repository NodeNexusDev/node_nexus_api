"""Unit tests for health service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.health_service import HealthService


class TestHealthServiceCheckDb:
    @pytest.mark.asyncio
    async def test_check_db_returns_ok(self) -> None:
        """check_db() returns ok status and detail when ping succeeds."""
        mock_repo = AsyncMock()
        mock_repo.ping.return_value = (True, "database reachable")

        service = HealthService(repository=mock_repo)
        status, detail = await service.check_db()

        assert status == "ok"
        assert detail == "database reachable"
        mock_repo.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_db_returns_error(self) -> None:
        """check_db() returns error status and detail when ping fails."""
        mock_repo = AsyncMock()
        mock_repo.ping.return_value = (False, "OperationalError")

        service = HealthService(repository=mock_repo)
        status, detail = await service.check_db()

        assert status == "error"
        assert detail == "OperationalError"
        mock_repo.ping.assert_called_once()


def test_scheduler_readiness_uses_application_port() -> None:
    scheduler = MagicMock()
    scheduler.is_ready.return_value = True
    scheduler.owns_execution.return_value = True
    scheduler.inspect.return_value = [MagicMock(), MagicMock()]
    service = HealthService(
        repository=AsyncMock(),
        scheduler=scheduler,
        scheduler_enabled=True,
    )

    status, detail = service.check_scheduler()
    assert status == "ok"
    assert "ready=True" in detail
    assert "owns=True" in detail
    assert "jobs=2" in detail
    scheduler.is_ready.assert_called_once_with()


def test_scheduler_readiness_disabled() -> None:
    service = HealthService(
        repository=AsyncMock(),
        scheduler=None,
        scheduler_enabled=False,
    )
    status, detail = service.check_scheduler()
    assert status == "ok"
    assert detail == "scheduler disabled"


def test_scheduler_readiness_not_ready() -> None:
    scheduler = MagicMock()
    scheduler.is_ready.return_value = False
    scheduler.owns_execution.return_value = False
    scheduler.inspect.return_value = []
    service = HealthService(
        repository=AsyncMock(),
        scheduler=scheduler,
        scheduler_enabled=True,
    )
    status, detail = service.check_scheduler()
    assert status == "error"
    assert "ready=False" in detail
