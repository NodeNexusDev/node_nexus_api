"""Tests for the Alembic migration lifecycle adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.lifecycle.migration_runner import MigrationRunner


class TestMigrationRunner:
    @patch("app.adapters.lifecycle.migration_runner.alembic_command")
    @patch("app.adapters.lifecycle.migration_runner.AlembicConfig")
    def test_run_sync_upgrades_to_head(
        self,
        config_cls: MagicMock,
        command: MagicMock,
    ) -> None:
        runner = MigrationRunner("postgresql+asyncpg://db/test")

        runner.run_sync()

        config_cls.assert_called_once_with("alembic.ini")
        config_cls.return_value.set_main_option.assert_called_once_with(
            "sqlalchemy.url", "postgresql+asyncpg://db/test"
        )
        command.upgrade.assert_called_once_with(config_cls.return_value, "head")

    @patch("app.adapters.lifecycle.migration_runner.alembic_command")
    def test_run_sync_wraps_alembic_failure(self, command: MagicMock) -> None:
        command.upgrade.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError, match="Database migrations failed"):
            MigrationRunner("postgresql+asyncpg://db/test").run_sync()

    @patch("app.adapters.lifecycle.migration_runner.asyncio.to_thread")
    async def test_run_uses_worker_thread(self, to_thread: AsyncMock) -> None:
        runner = MigrationRunner("postgresql+asyncpg://db/test")

        await runner.run()

        to_thread.assert_awaited_once_with(runner.run_sync)
