"""Tests for the startup audit cleanup use case."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from app.application.services.audit_cleanup_job import AuditCleanupJob


async def test_cleanup_job_deletes_expired_logs() -> None:
    writer = AsyncMock()
    writer.delete_before.return_value = 7

    deleted = await AuditCleanupJob(writer, retention_days=30).run()

    assert deleted == 7
    cutoff = writer.delete_before.call_args.args[0]
    expected = datetime.now(UTC) - timedelta(days=30)
    assert abs((cutoff - expected).total_seconds()) < 1


async def test_cleanup_job_skips_disabled_retention() -> None:
    writer = AsyncMock()

    assert await AuditCleanupJob(writer, retention_days=0).run() == 0
    writer.delete_before.assert_not_awaited()
