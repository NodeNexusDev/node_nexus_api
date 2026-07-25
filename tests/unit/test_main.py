"""Tests for app.main startup, migrations, and lifespan."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import _run_migrations, _run_migrations_sync, lifespan


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


class TestLifespan:
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
    ) -> None:
        mock_get_settings.return_value = MagicMock(LOG_LEVEL="info", DEBUG=False)
        mock_container.close = AsyncMock()

        from fastapi import FastAPI

        app = FastAPI()
        async with lifespan(app):
            mock_configure.assert_called_once_with(log_level="info", debug=False)
            mock_migrations.assert_called_once()

        mock_container.close.assert_awaited_once()
