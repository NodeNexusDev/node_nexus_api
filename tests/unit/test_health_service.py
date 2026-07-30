"""Unit tests for health service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.health_service import HealthService


class TestHealthServiceCheckDb:
    @pytest.mark.asyncio
    async def test_check_db_returns_true(self) -> None:
        """check_db() returns True when ping succeeds."""
        mock_repo = AsyncMock()
        mock_repo.ping.return_value = True

        service = HealthService(repository=mock_repo)
        result = await service.check_db()

        assert result is True
        mock_repo.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_db_returns_false(self) -> None:
        """check_db() returns False when ping fails."""
        mock_repo = AsyncMock()
        mock_repo.ping.return_value = False

        service = HealthService(repository=mock_repo)
        result = await service.check_db()

        assert result is False
        mock_repo.ping.assert_called_once()


def test_scheduler_readiness_uses_application_port() -> None:
    scheduler = MagicMock()
    scheduler.is_ready.return_value = True
    service = HealthService(
        repository=AsyncMock(),
        scheduler=scheduler,
        scheduler_enabled=True,
    )

    assert service.check_scheduler() is True
    scheduler.is_ready.assert_called_once_with()
