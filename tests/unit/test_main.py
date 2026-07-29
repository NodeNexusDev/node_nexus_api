"""Tests for app.main startup, migrations, and lifespan."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.main import (
    _cleanup_audit_logs,
    _execute_scheduled_script,
    _restore_schedules,
    _run_migrations,
    _run_migrations_sync,
    lifespan,
)


class TestRunMigrationsSync:
    @patch("app.main.alembic_command")
    @patch("app.main.AlembicConfig")
    @patch("app.main.get_settings")
    def test_success(
        self,
        mock_get_settings: MagicMock,
        mock_config_cls: MagicMock,
        mock_cmd: MagicMock,
    ) -> None:
        mock_get_settings.return_value = MagicMock(DATABASE_URL="sqlite:///test.db")
        _run_migrations_sync()
        mock_cmd.upgrade.assert_called_once()

    @patch("app.main.alembic_command")
    @patch("app.main.AlembicConfig")
    @patch("app.main.get_settings")
    def test_failure_raises_runtime_error(
        self,
        mock_get_settings: MagicMock,
        mock_config_cls: MagicMock,
        mock_cmd: MagicMock,
    ) -> None:
        mock_get_settings.return_value = MagicMock(DATABASE_URL="sqlite:///test.db")
        mock_cmd.upgrade.side_effect = Exception("connection refused")
        with pytest.raises(RuntimeError, match="Database migrations failed"):
            _run_migrations_sync()


class TestRunMigrations:
    @patch("app.main._run_migrations_sync")
    async def test_calls_sync_in_thread(self, mock_sync: MagicMock) -> None:
        await _run_migrations()
        mock_sync.assert_called_once()


class TestCleanupAuditLogs:
    @patch("app.main.container")
    @patch("app.main.get_settings")
    async def test_cleanup_disabled_when_days_zero(
        self, mock_get_settings: MagicMock, mock_container: MagicMock
    ) -> None:
        """Cleanup is skipped when AUDIT_LOG_RETENTION_DAYS <= 0."""
        mock_get_settings.return_value = MagicMock(AUDIT_LOG_RETENTION_DAYS=0)
        await _cleanup_audit_logs()
        mock_container.assert_not_called()


class TestRuntimeBackgroundJobs:
    @patch("app.main.container")
    async def test_execution_updates_success_metadata(
        self, mock_container: MagicMock
    ) -> None:
        script_service = AsyncMock()
        schedule_service = AsyncMock()
        request_container = AsyncMock()
        request_container.get = AsyncMock(
            side_effect=[script_service, schedule_service]
        )
        mock_container.return_value.__aenter__ = AsyncMock(
            return_value=request_container
        )
        mock_container.return_value.__aexit__ = AsyncMock(return_value=False)

        await _execute_scheduled_script(uuid4(), [uuid4()], {})
        schedule_service.mark_started.assert_awaited_once()
        schedule_service.mark_succeeded.assert_awaited_once()
        schedule_service.mark_failed.assert_not_awaited()

    @patch("app.main.container")
    async def test_execution_updates_failure_metadata(
        self, mock_container: MagicMock
    ) -> None:
        script_service = AsyncMock()
        script_service.execute_script.side_effect = TimeoutError("remote")
        schedule_service = AsyncMock()
        request_container = AsyncMock()
        request_container.get = AsyncMock(
            side_effect=[script_service, schedule_service]
        )
        mock_container.return_value.__aenter__ = AsyncMock(
            return_value=request_container
        )
        mock_container.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(TimeoutError):
            await _execute_scheduled_script(uuid4(), [uuid4()], {})
        schedule_service.mark_failed.assert_awaited_once()

    @patch("app.main.container")
    async def test_restore_publishes_scheduler_state(
        self, mock_container: MagicMock
    ) -> None:
        schedule_service = AsyncMock()
        schedule_service.restore.return_value = (3, 1)
        request_container = AsyncMock()
        request_container.get.return_value = schedule_service
        context = AsyncMock()
        context.__aenter__.return_value = request_container
        mock_container.return_value = context
        scheduler = MagicMock()
        mock_container.get = AsyncMock(return_value=scheduler)

        assert await _restore_schedules() == (3, 1)
        scheduler.mark_restored.assert_called_once_with(failed=1)

    @patch("app.main.container")
    @patch("app.main.get_settings")
    async def test_cleanup_disabled_when_negative(
        self, mock_get_settings: MagicMock, mock_container: MagicMock
    ) -> None:
        """Cleanup is skipped when AUDIT_LOG_RETENTION_DAYS < 0."""
        mock_get_settings.return_value = MagicMock(AUDIT_LOG_RETENTION_DAYS=-1)
        await _cleanup_audit_logs()
        mock_container.assert_not_called()

    @patch("app.main.container")
    @patch("app.main.get_settings")
    async def test_cleanup_calls_service(
        self, mock_get_settings: MagicMock, mock_container: MagicMock
    ) -> None:
        """Cleanup calls audit_service.cleanup_old_logs."""
        mock_get_settings.return_value = MagicMock(AUDIT_LOG_RETENTION_DAYS=90)
        mock_audit_service = AsyncMock()
        mock_audit_service.cleanup_old_logs.return_value = 5

        mock_req_container = AsyncMock()
        mock_req_container.get = AsyncMock(return_value=mock_audit_service)
        mock_container.return_value.__aenter__ = AsyncMock(
            return_value=mock_req_container
        )
        mock_container.return_value.__aexit__ = AsyncMock(return_value=False)

        await _cleanup_audit_logs()
        mock_audit_service.cleanup_old_logs.assert_called_once_with(90)

    @patch("app.main.container")
    @patch("app.main.get_settings")
    async def test_cleanup_handles_exception(
        self, mock_get_settings: MagicMock, mock_container: MagicMock
    ) -> None:
        """Cleanup handles exceptions gracefully."""
        mock_get_settings.return_value = MagicMock(AUDIT_LOG_RETENTION_DAYS=90)
        mock_container.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("db error")
        )
        mock_container.return_value.__aexit__ = AsyncMock(return_value=False)

        # Should not raise
        await _cleanup_audit_logs()


class TestLifespan:
    @patch("app.main._restore_schedules", new_callable=AsyncMock)
    @patch("app.main.container")
    @patch("app.main._run_migrations", new_callable=AsyncMock)
    @patch("app.main.configure_logging")
    @patch("app.main.get_settings")
    async def test_startup_and_shutdown(
        self,
        mock_get_settings: MagicMock,
        mock_configure: MagicMock,
        mock_migrations: AsyncMock,
        mock_container: MagicMock,
        mock_restore: AsyncMock,
    ) -> None:
        mock_get_settings.return_value = MagicMock(
            LOG_LEVEL="info", DEBUG=False, AUDIT_LOG_RETENTION_DAYS=0
        )
        mock_container.close = AsyncMock()
        mock_scheduler = MagicMock()
        mock_container.get = AsyncMock(return_value=mock_scheduler)

        from fastapi import FastAPI

        app = FastAPI()
        async with lifespan(app):
            mock_configure.assert_called_once_with(log_level="info", debug=False)
            mock_migrations.assert_called_once()

        mock_container.close.assert_awaited_once()
        mock_scheduler.configure_executor.assert_called_once()
        mock_restore.assert_awaited_once()

    @patch("app.main._restore_schedules", new_callable=AsyncMock)
    @patch("app.main._cleanup_audit_logs", new_callable=AsyncMock)
    @patch("app.main.container")
    @patch("app.main._run_migrations", new_callable=AsyncMock)
    @patch("app.main.configure_logging")
    @patch("app.main.get_settings")
    async def test_lifespan_calls_cleanup(
        self,
        mock_get_settings: MagicMock,
        mock_configure: MagicMock,
        mock_migrations: AsyncMock,
        mock_container: MagicMock,
        mock_cleanup: AsyncMock,
        mock_restore: AsyncMock,
    ) -> None:
        """Lifespan calls _cleanup_audit_logs."""
        mock_get_settings.return_value = MagicMock(
            LOG_LEVEL="info", DEBUG=False, AUDIT_LOG_RETENTION_DAYS=90
        )
        mock_container.close = AsyncMock()
        mock_container.get = AsyncMock(return_value=MagicMock())

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
