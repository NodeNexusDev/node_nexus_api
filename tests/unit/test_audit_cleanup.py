"""Unit tests for audit log cleanup."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.application.services.audit_log_service import AuditLogService


class TestAuditCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_old_logs(self) -> None:
        """Cleanup should delete logs older than retention days."""
        mock_repo = AsyncMock()
        mock_repo.delete_before.return_value = 10

        service = AuditLogService(reader=AsyncMock(), writer=mock_repo)
        deleted = await service.cleanup_old_logs(retention_days=30)

        assert deleted == 10
        mock_repo.delete_before.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_disabled_when_zero(self) -> None:
        """Cleanup should be disabled when retention_days is 0."""
        mock_repo = AsyncMock()

        service = AuditLogService(reader=AsyncMock(), writer=mock_repo)
        deleted = await service.cleanup_old_logs(retention_days=0)

        assert deleted == 0
        mock_repo.delete_before.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_disabled_when_negative(self) -> None:
        """Cleanup should be disabled when retention_days is negative."""
        mock_repo = AsyncMock()

        service = AuditLogService(reader=AsyncMock(), writer=mock_repo)
        deleted = await service.cleanup_old_logs(retention_days=-1)

        assert deleted == 0
        mock_repo.delete_before.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_calculates_correct_cutoff(self) -> None:
        """Cleanup should calculate correct cutoff date."""
        mock_repo = AsyncMock()
        mock_repo.delete_before.return_value = 5

        service = AuditLogService(reader=AsyncMock(), writer=mock_repo)
        await service.cleanup_old_logs(retention_days=90)

        call_args = mock_repo.delete_before.call_args
        cutoff = call_args[0][0]
        expected = datetime.now(UTC) - timedelta(days=90)
        # Allow 1 second tolerance
        assert abs((cutoff - expected).total_seconds()) < 1


class TestAuditDeleteAll:
    @pytest.mark.asyncio
    async def test_delete_all_logs(self) -> None:
        """Delete all should remove all audit log entries."""
        mock_repo = AsyncMock()
        mock_repo.delete_before.return_value = 100

        service = AuditLogService(reader=AsyncMock(), writer=mock_repo)
        deleted = await service.delete_all_logs()

        assert deleted == 100
        mock_repo.delete_before.assert_called_once()


class TestAuditLogRetentionConfig:
    def test_default_retention_days(self) -> None:
        """Default retention should be 90 days."""
        from app.core.config import Settings

        # We can't instantiate Settings without env vars, but we can check the field
        fields = Settings.model_fields
        assert "AUDIT_LOG_RETENTION_DAYS" in fields
        assert fields["AUDIT_LOG_RETENTION_DAYS"].default == 90
