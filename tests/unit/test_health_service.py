"""Unit tests for health service."""

from unittest.mock import AsyncMock

import pytest

from app.services.health_service import HealthService


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
