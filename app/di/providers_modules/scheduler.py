# ruff: noqa: I001
"""DI providers for the application."""

from __future__ import annotations

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.adapters.lifecycle.application_startup import ApplicationStartup
from app.adapters.lifecycle.migration_runner import MigrationRunner
from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker
from app.adapters.persistence.scheduler_ownership import SqlAlchemySchedulerOwnership
from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from app.adapters.runtime.scheduler import ApschedulerJobScheduler
from app.application.ports.audit_outbox_controller import AuditOutboxController
from app.application.ports.command_reader import CommandTemplateReader
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.scheduler_ownership import SchedulerOwnership
from app.application.ports.node_reader import NodeConnectionReader
from app.application.ports.remote_command import RemoteConnectorFactory
from app.application.ports.schedule import (
    JobSchedulerPort,
    ScheduleReader,
    ScheduleWriter,
)
from app.application.ports.script_persistence import (
    ScriptDefinitionReader,
    ScriptExecutionWriter,
)
from app.application.ports.user_persistence import UserReader, UserWriter
from app.application.services.audit_cleanup_job import AuditCleanupJob
from app.application.services.schedule_reconciliation import (
    ScheduleReconciliationService,
)
from app.application.services.schedule_restorer import ScheduleRestorer
from app.application.services.scheduled_script_executor import (
    ScheduledScriptExecutor,
)
from app.application.services.script_execution_service import ScriptExecutionService
from app.core.config import Settings


class SchedulerProvider(Provider):
    """Scheduler providers."""

    @provide(scope=Scope.APP)
    def get_scheduled_script_executor(
        self,
        script_reader: ScriptDefinitionReader,
        command_reader: CommandTemplateReader,
        node_reader: NodeConnectionReader,
        execution_writer: ScriptExecutionWriter,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        schedule_writer: ScheduleWriter,
    ) -> ScheduledScriptExecutor:
        """Compose the scheduler callback without a request service locator."""
        execution = ScriptExecutionService(
            script_reader=script_reader,
            command_reader=command_reader,
            node_reader=node_reader,
            execution_writer=execution_writer,
            credential_cipher=credential_cipher,
            connector_factory=connector_factory,
        )
        return ScheduledScriptExecutor(execution, schedule_writer)

    @provide(scope=Scope.APP)
    def get_schedule_reconciliation_service(
        self,
        reader: ScheduleReader,
        writer: ScheduleWriter,
        scheduler: JobSchedulerPort,
    ) -> ScheduleReconciliationService:
        """Compose persistent-to-runtime schedule reconciliation."""
        return ScheduleReconciliationService(reader, writer, scheduler)

    @provide(scope=Scope.APP)
    def get_schedule_restorer(
        self,
        reconciler: ScheduleReconciliationService,
        scheduler: JobSchedulerPort,
    ) -> ScheduleRestorer:
        """Get the persistent-to-runtime schedule restoration job."""
        return ScheduleRestorer(reconciler, scheduler)

    @provide(scope=Scope.APP)
    def get_job_scheduler(
        self, scheduler: ApschedulerRuntime
    ) -> ApschedulerJobScheduler:
        """Adapt the managed APScheduler runtime to the application port."""
        return ApschedulerJobScheduler(scheduler)

    @provide(scope=Scope.APP, provides=JobSchedulerPort)
    def get_job_scheduler_port(
        self, scheduler: ApschedulerJobScheduler
    ) -> JobSchedulerPort:
        """Bind runtime schedule operations."""
        return scheduler

    @provide(scope=Scope.APP, provides=SchedulerOwnership)
    def get_scheduler_ownership(self, engine: AsyncEngine) -> SchedulerOwnership:
        """Provide the PostgreSQL advisory-lock ownership port."""
        return SqlAlchemySchedulerOwnership(engine)

    @provide(scope=Scope.APP)
    async def get_script_scheduler(
        self, engine: AsyncEngine, settings: Settings
    ) -> AsyncIterable[ApschedulerRuntime]:
        """Start and finalize the application-scoped script scheduler."""
        ownership = SqlAlchemySchedulerOwnership(engine)
        scheduler = ApschedulerRuntime(
            ownership=ownership,
            ownership_poll_seconds=settings.SCHEDULER_OWNERSHIP_POLL_SECONDS,
        )
        if settings.SCHEDULER_ENABLED:
            await scheduler.acquire_ownership()
            scheduler.start_ownership_monitor()
            await scheduler.start()
        try:
            yield scheduler
        finally:
            await scheduler.stop()

    @provide(scope=Scope.APP)
    async def get_audit_outbox_worker(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AuditOutboxWorker]:
        """Run durable audit delivery for the application lifetime."""
        worker = AuditOutboxWorker(sessionmaker)
        try:
            yield worker
        finally:
            await worker.stop()

    @provide(scope=Scope.APP)
    def get_audit_outbox_controller(
        self, worker: AuditOutboxWorker
    ) -> AuditOutboxController:
        """Expose audit outbox lifecycle through the application port."""
        return worker

    @provide(scope=Scope.APP)
    def get_application_startup(
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
    ) -> ApplicationStartup:
        """Compose the application lifecycle startup adapter."""
        return ApplicationStartup(
            settings=settings,
            migration_runner=migration_runner,
            scheduler=scheduler,
            scheduled_executor=scheduled_executor,
            schedule_restorer=schedule_restorer,
            audit_cleanup=audit_cleanup,
            audit_worker=audit_worker,
            user_reader=user_reader,
            user_writer=user_writer,
        )
