"""DI providers for the application."""

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.script_gateway import (
    ScopedScriptDefinitionReader,
    ScopedScriptExecutionWriter,
)
from app.application.services.streaming_command_service import StreamingCommandService
from app.core.config import Settings, get_settings
from app.core.connectors.ssh import SSHConnectorFactory
from app.core.scheduler import ScriptScheduler
from app.repositories.api_key_repo import APIKeyRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.command_repo import CommandRepository
from app.repositories.health_repo import HealthRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.repositories.script_schedule_repo import ScriptScheduleRepository
from app.services.api_key_service import APIKeyService
from app.services.audit_outbox_worker import AuditOutboxWorker
from app.services.audit_service import AuditService, RequiredAuditWriter
from app.services.command_service import CommandService
from app.services.config_service import ConfigService
from app.services.docker_service import DockerService
from app.services.health_service import HealthService
from app.services.node_bulk_command_service import NodeBulkCommandService
from app.services.node_command_service import NodeCommandService
from app.services.node_management_service import NodeManagementService
from app.services.node_metrics_service import NodeMetricsService
from app.services.schedule_service import ScheduleService
from app.services.script_service import ScriptService


class DbProvider(Provider):
    """Database session provider."""

    @provide(scope=Scope.APP)
    async def get_engine(self, settings: Settings) -> AsyncIterable[AsyncEngine]:
        """Get the application engine and dispose its pool on shutdown."""
        engine = create_async_engine(settings.DATABASE_URL)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide(scope=Scope.APP)
    def get_sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """Get a session maker bound to the managed application engine."""
        return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @provide(scope=Scope.REQUEST)
    async def get_session(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        """Get a database session with transaction management."""
        async with sessionmaker() as session:
            async with session.begin():
                yield session


class RepositoryProvider(Provider):
    """Repository providers."""

    @provide(scope=Scope.APP)
    def get_scoped_script_reader(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedScriptDefinitionReader:
        """Get a script reader that owns a short session per operation."""
        return ScopedScriptDefinitionReader(sessionmaker)

    @provide(scope=Scope.APP)
    def get_scoped_execution_writer(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedScriptExecutionWriter:
        """Get a writer that commits execution transitions independently."""
        return ScopedScriptExecutionWriter(sessionmaker)

    @provide(scope=Scope.APP)
    def get_scoped_command_reader(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedCommandTemplateReader:
        """Get a command reader that owns a short session per operation."""
        return ScopedCommandTemplateReader(sessionmaker)

    @provide(scope=Scope.APP)
    def get_scoped_node_reader(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedNodeConnectionReader:
        """Get a node reader that owns a short session per operation."""
        return ScopedNodeConnectionReader(sessionmaker)

    @provide(scope=Scope.REQUEST)
    def get_node_repository(self, session: AsyncSession) -> NodeRepository:
        """Get node repository."""
        return NodeRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_audit_repository(self, session: AsyncSession) -> AuditLogRepository:
        """Get audit log repository."""
        return AuditLogRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_command_repository(self, session: AsyncSession) -> CommandRepository:
        """Get command repository."""
        return CommandRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_script_repository(self, session: AsyncSession) -> ScriptRepository:
        """Get script repository."""
        return ScriptRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_script_execution_repository(
        self, session: AsyncSession
    ) -> ScriptExecutionRepository:
        """Get script execution repository."""
        return ScriptExecutionRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_script_schedule_repository(
        self, session: AsyncSession
    ) -> ScriptScheduleRepository:
        """Get persistent script schedule repository."""
        return ScriptScheduleRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_api_key_repository(self, session: AsyncSession) -> APIKeyRepository:
        """Get API key repository."""
        return APIKeyRepository(session)

    @provide(scope=Scope.REQUEST)
    def get_health_repository(self, session: AsyncSession) -> HealthRepository:
        """Get health check repository."""
        return HealthRepository(session)


class ConnectorProvider(Provider):
    """Connector providers."""

    @provide(scope=Scope.APP)
    def get_ssh_connector_factory(self, settings: Settings) -> SSHConnectorFactory:
        """Get SSH connector factory."""
        return SSHConnectorFactory(
            known_hosts_path=settings.SSH_KNOWN_HOSTS_PATH,
            strict_host_key_checking=settings.SSH_STRICT_HOST_KEY_CHECKING,
        )


class ServiceProvider(Provider):
    """Service providers."""

    @provide(scope=Scope.REQUEST)
    def get_node_metrics_service(
        self,
        connector_factory: SSHConnectorFactory,
        node_reader: ScopedNodeConnectionReader,
    ) -> NodeMetricsService:
        """Get the node metrics service."""
        return NodeMetricsService(
            connector_factory=connector_factory,
            node_reader=node_reader,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_bulk_command_service(
        self,
        repository: NodeRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
        node_reader: ScopedNodeConnectionReader,
    ) -> NodeBulkCommandService:
        """Get the bulk SSH command service."""
        return NodeBulkCommandService(
            repository=repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_command_service(
        self,
        repository: NodeRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
        node_reader: ScopedNodeConnectionReader,
    ) -> NodeCommandService:
        """Get the single-node SSH command service."""
        return NodeCommandService(
            repository=repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
        )

    @provide(scope=Scope.REQUEST)
    def get_streaming_command_service(
        self,
        node_reader: ScopedNodeConnectionReader,
        connector_factory: SSHConnectorFactory,
    ) -> StreamingCommandService:
        """Get WebSocket streaming orchestration service."""
        return StreamingCommandService(node_reader, connector_factory)

    @provide(scope=Scope.REQUEST)
    def get_audit_service(
        self,
        repository: AuditLogRepository,
        required_writer: RequiredAuditWriter,
    ) -> AuditService:
        """Get audit service."""
        return AuditService(
            repository=repository,
            required_writer=required_writer,
        )

    @provide(scope=Scope.APP)
    def get_required_audit_writer(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> RequiredAuditWriter:
        """Get the independent writer for pre-side-effect audit intents."""
        return RequiredAuditWriter(sessionmaker)

    @provide(scope=Scope.REQUEST)
    def get_node_management_service(
        self,
        repository: NodeRepository,
        audit_service: AuditService,
    ) -> NodeManagementService:
        """Get the node management service."""
        return NodeManagementService(
            repository=repository,
            audit_service=audit_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_command_service(
        self,
        repository: CommandRepository,
        node_repository: NodeRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
        command_reader: ScopedCommandTemplateReader,
        node_reader: ScopedNodeConnectionReader,
    ) -> CommandService:
        """Get command service."""
        return CommandService(
            repository=repository,
            node_repository=node_repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
            command_reader=command_reader,
            node_reader=node_reader,
        )

    @provide(scope=Scope.REQUEST)
    def get_script_service(
        self,
        repository: ScriptRepository,
        command_repository: CommandRepository,
        node_repository: NodeRepository,
        execution_repository: ScriptExecutionRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
        script_reader: ScopedScriptDefinitionReader,
        command_reader: ScopedCommandTemplateReader,
        node_reader: ScopedNodeConnectionReader,
        execution_writer: ScopedScriptExecutionWriter,
    ) -> ScriptService:
        """Get script service."""
        return ScriptService(
            repository=repository,
            command_repository=command_repository,
            node_repository=node_repository,
            execution_repository=execution_repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
            script_reader=script_reader,
            command_reader=command_reader,
            node_reader=node_reader,
            execution_writer=execution_writer,
        )

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(self, repository: APIKeyRepository) -> APIKeyService:
        """Get API key service."""
        return APIKeyService(repository=repository)

    @provide(scope=Scope.REQUEST)
    def get_docker_service(
        self,
        repository: NodeRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
        node_reader: ScopedNodeConnectionReader,
    ) -> DockerService:
        """Get Docker service."""
        return DockerService(
            repository=repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
        )

    @provide(scope=Scope.REQUEST)
    def get_health_service(
        self,
        repository: HealthRepository,
        scheduler: ScriptScheduler,
        settings: Settings,
    ) -> HealthService:
        """Get health check service."""
        return HealthService(
            repository=repository,
            scheduler=scheduler,
            scheduler_enabled=settings.SCHEDULER_ENABLED,
        )

    @provide(scope=Scope.REQUEST)
    def get_config_service(
        self,
        node_repository: NodeRepository,
        command_repository: CommandRepository,
        script_repository: ScriptRepository,
    ) -> ConfigService:
        """Get configuration import/export service."""
        return ConfigService(
            node_repository=node_repository,
            command_repository=command_repository,
            script_repository=script_repository,
        )

    @provide(scope=Scope.REQUEST)
    def get_schedule_service(
        self,
        repository: ScriptScheduleRepository,
        script_repository: ScriptRepository,
        node_repository: NodeRepository,
        scheduler: ScriptScheduler,
    ) -> ScheduleService:
        """Get the persistent schedule application service."""
        return ScheduleService(
            repository=repository,
            script_repository=script_repository,
            node_repository=node_repository,
            scheduler=scheduler,
        )


class ConfigProvider(Provider):
    """Configuration provider."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Get application settings."""
        return get_settings()


class SchedulerProvider(Provider):
    """Scheduler providers."""

    @provide(scope=Scope.APP)
    async def get_script_scheduler(
        self, engine: AsyncEngine, settings: Settings
    ) -> AsyncIterable[ScriptScheduler]:
        """Start and finalize the application-scoped script scheduler."""
        scheduler = ScriptScheduler()
        if settings.SCHEDULER_ENABLED:
            await scheduler.acquire_ownership(engine)
            scheduler.start_ownership_monitor(engine)
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
        worker.start()
        try:
            yield worker
        finally:
            await worker.stop()


class AppProvider(
    ConfigProvider,
    DbProvider,
    RepositoryProvider,
    ConnectorProvider,
    SchedulerProvider,
    ServiceProvider,
):
    """Main application provider."""

    pass
