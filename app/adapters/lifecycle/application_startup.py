"""Application startup orchestration at the infrastructure boundary."""

import structlog

from app.adapters.lifecycle.migration_runner import MigrationRunner
from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker
from app.application.services.audit_cleanup_job import AuditCleanupJob
from app.application.services.schedule_restorer import ScheduleRestorer
from app.application.services.scheduled_script_executor import (
    ScheduledScriptExecutor,
)
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.scheduler import ScriptScheduler

logger = structlog.get_logger()


class ApplicationStartup:
    """Wire and execute application-scoped startup jobs."""

    def __init__(
        self,
        settings: Settings,
        migration_runner: MigrationRunner,
        scheduler: ScriptScheduler,
        scheduled_executor: ScheduledScriptExecutor,
        schedule_restorer: ScheduleRestorer,
        audit_cleanup: AuditCleanupJob,
        audit_worker: AuditOutboxWorker,
    ) -> None:
        self._settings = settings
        self._migration_runner = migration_runner
        self._scheduler = scheduler
        self._scheduled_executor = scheduled_executor
        self._schedule_restorer = schedule_restorer
        self._audit_cleanup = audit_cleanup
        self._audit_worker = audit_worker

    async def run(self) -> None:
        """Configure runtime components and execute startup jobs."""
        configure_logging(
            log_level=self._settings.LOG_LEVEL,
            debug=self._settings.DEBUG,
        )
        logger.info("app.startup")
        await self._run_migrations()
        self._scheduler.configure_executor(self._scheduled_executor.execute)
        await self._restore_schedules()
        await self._cleanup_audit()

    async def _run_migrations(self) -> None:
        if not self._settings.AUTO_MIGRATE:
            logger.info("migrations.skipped", reason="AUTO_MIGRATE is disabled")
            return
        await self._migration_runner.run()
        logger.info("migrations.applied")

    async def _restore_schedules(self) -> None:
        if not self._settings.SCHEDULER_ENABLED:
            self._schedule_restorer.mark_disabled()
            return

        async def restore() -> tuple[int, int]:
            result = await self._schedule_restorer.run()
            logger.info(
                "scheduler.restore.completed",
                restored=result.restored,
                failed=result.failed,
            )
            return result.restored, result.failed

        self._scheduler.configure_reconciler(restore)
        await restore()
        self._scheduler.start_reconciliation()

    async def _cleanup_audit(self) -> None:
        try:
            deleted = await self._audit_cleanup.run()
            if deleted > 0:
                logger.info("audit.cleanup.startup", deleted=deleted)
        except Exception:
            logger.warning("audit.cleanup.startup.failed")
