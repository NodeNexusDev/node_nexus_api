"""Unit tests for health repository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.health_repo import HealthRepository


class TestHealthRepositoryPing:
    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        """ping() returns True when SELECT 1 succeeds."""
        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        repo = HealthRepository(session=mock_session)
        result = await repo.ping()

        assert result is True
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_failure(self) -> None:
        """ping() returns False when SELECT 1 fails."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Connection failed")

        repo = HealthRepository(session=mock_session)
        result = await repo.ping()

        assert result is False

    @pytest.mark.asyncio
    async def test_ping_database_error(self) -> None:
        """ping() returns False on database error."""
        from sqlalchemy.exc import OperationalError

        mock_session = AsyncMock()
        mock_session.execute.side_effect = OperationalError(
            "connection refused", {}, None
        )

        repo = HealthRepository(session=mock_session)
        result = await repo.ping()

        assert result is False
