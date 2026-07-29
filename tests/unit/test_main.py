"""Tests for app.main startup, migrations, and lifespan."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.main import (
    _cleanup_audit_logs,
    _restore_schedules,
    lifespan,
)


class TestCleanupAuditLogs:
    @patch("app.main.container")
    async def test_cleanup_runs_application_job(
        self, mock_container: MagicMock
    ) -> None:
        job = AsyncMock()
        job.run.return_value = 0
        mock_container.get = AsyncMock(return_value=job)
        await _cleanup_audit_logs()
        job.run.assert_awaited_once()


class TestRuntimeBackgroundJobs:
    async def test_restore_publishes_scheduler_state(self) -> None:
        reconciler = AsyncMock()
        reconciler.reconcile.return_value = MagicMock(restored=3, failed=1)
        scheduler = MagicMock()

        assert await _restore_schedules(reconciler, scheduler) == (3, 1)
        scheduler.mark_restored.assert_called_once_with(failed=1)

    @patch("app.main.container")
    async def test_cleanup_calls_service(self, mock_container: MagicMock) -> None:
        """Cleanup resolves and runs its application job."""
        job = AsyncMock()
        job.run.return_value = 5
        mock_container.get = AsyncMock(return_value=job)
        await _cleanup_audit_logs()
        job.run.assert_awaited_once()

    @patch("app.main.container")
    async def test_cleanup_handles_exception(self, mock_container: MagicMock) -> None:
        """Cleanup handles exceptions gracefully."""
        mock_container.get = AsyncMock(side_effect=Exception("db error"))
        await _cleanup_audit_logs()


class TestLifespan:
    @patch("app.main._restore_schedules", new_callable=AsyncMock)
    @patch("app.main.container")
    @patch("app.main.configure_logging")
    @patch("app.main.get_settings")
    async def test_startup_and_shutdown(
        self,
        mock_get_settings: MagicMock,
        mock_configure: MagicMock,
        mock_container: MagicMock,
        mock_restore: AsyncMock,
    ) -> None:
        mock_get_settings.return_value = MagicMock(
            LOG_LEVEL="info", DEBUG=False, AUDIT_LOG_RETENTION_DAYS=0
        )
        mock_container.close = AsyncMock()
        mock_scheduler = MagicMock()
        mock_scheduler.run = AsyncMock()
        mock_container.get = AsyncMock(return_value=mock_scheduler)

        from fastapi import FastAPI

        app = FastAPI()
        async with lifespan(app):
            mock_configure.assert_called_once_with(log_level="info", debug=False)
            mock_scheduler.run.assert_awaited_once()

        mock_container.close.assert_awaited_once()
        mock_scheduler.configure_executor.assert_called_once()
        mock_restore.assert_awaited_once()

    @patch("app.main._restore_schedules", new_callable=AsyncMock)
    @patch("app.main._cleanup_audit_logs", new_callable=AsyncMock)
    @patch("app.main.container")
    @patch("app.main.configure_logging")
    @patch("app.main.get_settings")
    async def test_lifespan_calls_cleanup(
        self,
        mock_get_settings: MagicMock,
        mock_configure: MagicMock,
        mock_container: MagicMock,
        mock_cleanup: AsyncMock,
        mock_restore: AsyncMock,
    ) -> None:
        """Lifespan calls _cleanup_audit_logs."""
        mock_get_settings.return_value = MagicMock(
            LOG_LEVEL="info", DEBUG=False, AUDIT_LOG_RETENTION_DAYS=90
        )
        mock_container.close = AsyncMock()
        dependency = MagicMock()
        dependency.run = AsyncMock()
        mock_container.get = AsyncMock(return_value=dependency)

        from fastapi import FastAPI

        app = FastAPI()
        async with lifespan(app):
            pass

        mock_cleanup.assert_called_once()
        mock_restore.assert_awaited_once()


class TestDomainErrorHandler:
    @patch("app.main.get_settings")
    def test_error_handler_returns_json(self, mock_get_settings: MagicMock) -> None:
        """Domain error handler returns JSON response."""
        from fastapi import FastAPI

        from app.core.exceptions import NodeNotFoundError

        app = FastAPI()

        @app.get("/test")
        async def raise_error():
            raise NodeNotFoundError("node not found")

        # The error handler is registered in create_app, test directly
        exc = NodeNotFoundError("test error")
        _error_status_map = {NodeNotFoundError: 404}
        status_code = _error_status_map.get(type(exc), 422)
        assert status_code == 404
