"""Unit tests for health repository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.persistence.dao.health import HealthRepository


class TestHealthRepositoryPing:
    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        """ping() returns (True, detail) when SELECT 1 succeeds."""
        mock_session = AsyncMock()
        mock_session.execute.return_value = MagicMock()

        repo = HealthRepository(session=mock_session)
        ok, detail = await repo.ping()

        assert ok is True
        assert detail == "database reachable"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_failure(self) -> None:
        """ping() returns (False, exception_type) when SELECT 1 fails."""
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Connection failed")

        repo = HealthRepository(session=mock_session)
        ok, detail = await repo.ping()

        assert ok is False
        assert detail == "Exception"

    @pytest.mark.asyncio
    async def test_ping_database_error(self) -> None:
        """ping() returns (False, exception_type) on database error."""
        from sqlalchemy.exc import OperationalError

        mock_session = AsyncMock()
        mock_session.execute.side_effect = OperationalError(
            "connection refused", {}, None
        )

        repo = HealthRepository(session=mock_session)
        ok, detail = await repo.ping()

        assert ok is False
        assert detail == "OperationalError"
