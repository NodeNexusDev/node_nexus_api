"""Tests for application startup orchestration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.lifecycle.application_startup import ApplicationStartup


def _startup(
    *,
    auto_migrate: bool = True,
    scheduler_enabled: bool = True,
) -> tuple[ApplicationStartup, dict[str, MagicMock]]:
    dependencies = {
        "migration": MagicMock(run=AsyncMock()),
        "scheduler": MagicMock(),
        "executor": MagicMock(),
        "restorer": MagicMock(),
        "cleanup": MagicMock(run=AsyncMock(return_value=0)),
        "worker": MagicMock(),
        "user_reader": MagicMock(get_by_email=AsyncMock(return_value=None)),
        "user_writer": MagicMock(create_user=AsyncMock()),
    }
    dependencies["restorer"].run = AsyncMock(
        return_value=MagicMock(restored=2, failed=0)
    )
    settings = MagicMock(
        LOG_LEVEL="info",
        DEBUG=False,
        AUTO_MIGRATE=auto_migrate,
        SCHEDULER_ENABLED=scheduler_enabled,
        INITIAL_SUPERUSER_EMAIL="",
        INITIAL_SUPERUSER_PASSWORD="",
    )
    startup = ApplicationStartup(
        settings=settings,
        migration_runner=dependencies["migration"],
        scheduler=dependencies["scheduler"],
        scheduled_executor=dependencies["executor"],
        schedule_restorer=dependencies["restorer"],
        audit_cleanup=dependencies["cleanup"],
        audit_worker=dependencies["worker"],
        user_reader=dependencies["user_reader"],
        user_writer=dependencies["user_writer"],
    )
    return startup, dependencies


@patch("app.adapters.lifecycle.application_startup.configure_logging")
async def test_runs_enabled_startup_components(configure: MagicMock) -> None:
    startup, dependencies = _startup()

    await startup.run()

    configure.assert_called_once_with(log_level="info", debug=False)
    dependencies["migration"].run.assert_awaited_once()
    dependencies["worker"].start.assert_called_once()
    dependencies["scheduler"].configure_executor.assert_called_once_with(
        dependencies["executor"].execute
    )
    dependencies["restorer"].run.assert_awaited_once()
    dependencies["scheduler"].start_reconciliation.assert_called_once()
    dependencies["cleanup"].run.assert_awaited_once()


async def test_skips_disabled_migrations_and_scheduler() -> None:
    startup, dependencies = _startup(
        auto_migrate=False,
        scheduler_enabled=False,
    )

    await startup.run()

    dependencies["migration"].run.assert_not_awaited()
    dependencies["worker"].start.assert_called_once()
    dependencies["restorer"].run.assert_not_awaited()
    dependencies["restorer"].mark_disabled.assert_called_once()


async def test_audit_cleanup_failure_does_not_abort_startup() -> None:
    startup, dependencies = _startup()
    dependencies["cleanup"].run.side_effect = RuntimeError("db unavailable")

    await startup.run()

    dependencies["scheduler"].start_reconciliation.assert_called_once()


async def test_configured_initial_superuser_is_created() -> None:
    startup, dependencies = _startup()
    startup._settings.INITIAL_SUPERUSER_EMAIL = "admin@example.com"
    startup._settings.INITIAL_SUPERUSER_PASSWORD = "strong-password"

    await startup.run()

    dependencies["user_reader"].get_by_email.assert_awaited_once_with(
        "admin@example.com"
    )
    dependencies["user_writer"].create_user.assert_awaited_once()


async def test_initial_superuser_failure_aborts_startup() -> None:
    startup, dependencies = _startup()
    startup._settings.INITIAL_SUPERUSER_EMAIL = "admin@example.com"
    startup._settings.INITIAL_SUPERUSER_PASSWORD = "strong-password"
    dependencies["user_writer"].create_user.side_effect = RuntimeError(
        "database unavailable"
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await startup.run()

    dependencies["worker"].start.assert_not_called()
