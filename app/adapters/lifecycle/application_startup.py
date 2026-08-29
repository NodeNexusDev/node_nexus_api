"""Application startup orchestration at the infrastructure boundary."""

from pathlib import Path

import structlog

from app.adapters.lifecycle.migration_runner import MigrationRunner
from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker
from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from app.application.dto.user import UserCreateDTO
from app.application.ports.user_persistence import UserReader, UserWriter
from app.application.services.audit_cleanup_job import AuditCleanupJob
from app.application.services.schedule_restorer import ScheduleRestorer
from app.application.services.scheduled_script_executor import (
    ScheduledScriptExecutor,
)
from app.core.config import Settings
from app.core.logging import configure_logging

logger = structlog.get_logger()


class ApplicationStartup:
    """Wire and execute application-scoped startup jobs."""

    def __init__(
        self,
        settings: Settings,
        migration_runner: MigrationRunner,
        scheduler: ApschedulerRuntime,
        scheduled_executor: ScheduledScriptExecutor,
        schedule_restorer: ScheduleRestorer,
        audit_cleanup: AuditCleanupJob,
        audit_worker: AuditOutboxWorker,
        user_reader: UserReader,
        user_writer: UserWriter,
    ) -> None:
        self._settings = settings
        self._migration_runner = migration_runner
        self._scheduler = scheduler
        self._scheduled_executor = scheduled_executor
        self._schedule_restorer = schedule_restorer
        self._audit_cleanup = audit_cleanup
        self._audit_worker = audit_worker
        self._user_reader = user_reader
        self._user_writer = user_writer

    async def run(self) -> None:
        """Configure runtime components and execute startup jobs."""
        configure_logging(
            log_level=self._settings.LOG_LEVEL,
            debug=self._settings.DEBUG,
        )
        logger.info("app.startup")
        await self._ensure_known_hosts()
        await self._run_migrations()
        await self._ensure_initial_superuser()
        self._audit_worker.start()
        self._scheduler.configure_executor(self._scheduled_executor.execute)
        await self._restore_schedules()
        await self._cleanup_audit()

    async def _ensure_known_hosts(self) -> None:
        """Create known_hosts directory/file so strict mode has a file to check."""
        path = Path(self._settings.SSH_KNOWN_HOSTS_PATH)
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not path.exists():
                path.touch(mode=0o644, exist_ok=True)
                path.chmod(0o644)
                logger.info("startup.known_hosts.created", path=str(path))
            else:
                try:
                    path.chmod(0o644)
                except OSError:
                    pass
        except OSError as exc:
            logger.warning("startup.known_hosts.failed", path=str(path), error=str(exc))

    async def _run_migrations(self) -> None:
        if not self._settings.AUTO_MIGRATE:
            logger.info("migrations.skipped", reason="AUTO_MIGRATE is disabled")
            return
        await self._migration_runner.run()
        logger.info("migrations.applied")

    async def _ensure_initial_superuser(self) -> None:
        """Create initial superuser from env vars if no users exist."""
        email = self._settings.INITIAL_SUPERUSER_EMAIL
        password = self._settings.INITIAL_SUPERUSER_PASSWORD
        if not email or not password:
            return

        try:
            existing = await self._user_reader.get_by_email(email)
            if existing is not None:
                logger.info("startup.superuser.exists", email=email)
                return

            await self._user_writer.create_user(
                UserCreateDTO(email=email, password=password, is_superuser=True)
            )
            logger.info("startup.superuser.created", email=email)
        except Exception:
            logger.exception("startup.superuser.failed", email=email)
            raise

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
        self._scheduler.start_reconciliation(
            interval_seconds=self._settings.SCHEDULER_RECONCILIATION_INTERVAL_SECONDS,
        )

    async def _cleanup_audit(self) -> None:
        try:
            deleted = await self._audit_cleanup.run()
            if deleted > 0:
                logger.info("audit.cleanup.startup", deleted=deleted)
        except Exception:
            logger.warning("audit.cleanup.startup.failed")
