"""DI providers for the application."""

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.persistence.command_management import SqlAlchemyCommandGateway
from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
from app.adapters.persistence.node_management import (
    SqlAlchemyNodeManagementGateway,
)
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.schedule import SqlAlchemyScheduleGateway
from app.adapters.persistence.script_gateway import (
    ScopedScriptDefinitionReader,
    ScopedScriptExecutionWriter,
    SqlAlchemyScriptGateway,
)
from app.adapters.runtime.docker import SshDockerRuntime
from app.adapters.runtime.scheduler import ApschedulerJobScheduler
from app.adapters.security import AesGcmCredentialCipher
from app.application.ports.audit_sink import AuditEventSink
from app.application.ports.command_management import CommandReader, CommandWriter
from app.application.ports.command_reader import CommandTemplateReader
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.docker_runtime import DockerRuntime
from app.application.ports.node_management import (
    NodeManagementReader,
    NodeManagementWriter,
)
from app.application.ports.node_reader import NodeConnectionReader, NodeStatusWriter
from app.application.ports.remote_command import RemoteConnectorFactory
from app.application.ports.schedule import (
    JobSchedulerPort,
    ScheduleReader,
    ScheduleWriter,
)
from app.application.ports.script_persistence import (
    ScriptDefinitionReader,
    ScriptExecutionReader,
    ScriptExecutionWriter,
    ScriptReader,
    ScriptWriter,
)
from app.application.services.schedule_management import (
    ScheduleManagementService,
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
from app.services.command_execution_service import CommandExecutionService
from app.services.command_management_service import CommandManagementService
from app.services.config_service import ConfigService
from app.services.docker.bulk_service import DockerBulkService
from app.services.docker.command_runner import DockerCommandRunner
from app.services.docker.container_service import DockerContainerService
from app.services.docker.image_service import DockerImageService
from app.services.docker.resource_service import DockerResourceService
from app.services.health_service import HealthService
from app.services.node_bulk_command_service import NodeBulkCommandService
from app.services.node_command_service import NodeCommandService
from app.services.node_management_service import NodeManagementService
from app.services.node_metrics_service import NodeMetricsService
from app.services.schedule_service import ScheduleService
from app.services.script_execution_service import ScriptExecutionService
from app.services.script_history_service import ScriptHistoryService
from app.services.script_management_service import ScriptManagementService


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
    def get_script_execution_writer(
        self, writer: ScopedScriptExecutionWriter
    ) -> ScriptExecutionWriter:
        """Bind independent execution transitions to the writer port."""
        return writer

    @provide(scope=Scope.APP)
    def get_script_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyScriptGateway:
        """Get the short-scope script persistence gateway."""
        return SqlAlchemyScriptGateway(sessionmaker)

    @provide(scope=Scope.APP)
    def get_script_reader(self, gateway: SqlAlchemyScriptGateway) -> ScriptReader:
        """Bind the script reader port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_script_writer(self, gateway: SqlAlchemyScriptGateway) -> ScriptWriter:
        """Bind the script writer port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_script_execution_reader(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptExecutionReader:
        """Bind the execution history reader port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_script_definition_reader(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptDefinitionReader:
        """Bind script definitions to the script gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_scoped_command_reader(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedCommandTemplateReader:
        """Get a command reader that owns a short session per operation."""
        return ScopedCommandTemplateReader(sessionmaker)

    @provide(scope=Scope.APP)
    def get_command_management_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyCommandGateway:
        """Get the short-scope command management gateway."""
        return SqlAlchemyCommandGateway(sessionmaker)

    @provide(scope=Scope.APP)
    def get_command_management_reader(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandReader:
        """Bind the command management reader port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_command_management_writer(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandWriter:
        """Bind the command management writer port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_command_template_reader(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandTemplateReader:
        """Bind command execution templates to the management gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_scoped_node_reader(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedNodeConnectionReader:
        """Get a node reader that owns a short session per operation."""
        return ScopedNodeConnectionReader(sessionmaker)

    @provide(scope=Scope.APP)
    def get_node_connection_reader(
        self, reader: ScopedNodeConnectionReader
    ) -> NodeConnectionReader:
        """Bind the node connection reader port."""
        return reader

    @provide(scope=Scope.APP)
    def get_node_management_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyNodeManagementGateway:
        """Get the short-scope node management gateway."""
        return SqlAlchemyNodeManagementGateway(sessionmaker)

    @provide(scope=Scope.APP)
    def get_node_management_reader(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeManagementReader:
        """Bind the node management reader port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_node_management_writer(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeManagementWriter:
        """Bind the node management writer port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_node_status_writer(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeStatusWriter:
        """Bind the node status writer port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_schedule_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyScheduleGateway:
        """Get the short-scope persistent schedule gateway."""
        return SqlAlchemyScheduleGateway(sessionmaker)

    @provide(scope=Scope.APP)
    def get_schedule_reader(self, gateway: SqlAlchemyScheduleGateway) -> ScheduleReader:
        """Bind persistent schedule reads."""
        return gateway

    @provide(scope=Scope.APP)
    def get_schedule_writer(self, gateway: SqlAlchemyScheduleGateway) -> ScheduleWriter:
        """Bind persistent schedule writes."""
        return gateway

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

    @provide(scope=Scope.APP)
    def get_remote_connector_factory(
        self, factory: SSHConnectorFactory
    ) -> RemoteConnectorFactory:
        """Bind remote command sessions to the SSH adapter."""
        return factory

    @provide(scope=Scope.APP)
    def get_credential_cipher(self) -> CredentialCipher:
        """Bind credential protection to the configured AES-GCM adapter."""
        return AesGcmCredentialCipher()

    @provide(scope=Scope.APP)
    def get_docker_runtime(
        self,
        connector_factory: RemoteConnectorFactory,
        credential_cipher: CredentialCipher,
    ) -> DockerRuntime:
        """Bind Docker CLI execution to the SSH runtime adapter."""
        return SshDockerRuntime(connector_factory, credential_cipher)


class ServiceProvider(Provider):
    """Service providers."""

    @provide(scope=Scope.REQUEST)
    def get_node_metrics_service(
        self,
        connector_factory: RemoteConnectorFactory,
        node_reader: ScopedNodeConnectionReader,
        credential_cipher: CredentialCipher,
    ) -> NodeMetricsService:
        """Get the node metrics service."""
        return NodeMetricsService(
            connector_factory=connector_factory,
            node_reader=node_reader,
            credential_cipher=credential_cipher,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_bulk_command_service(
        self,
        audit_service: AuditEventSink,
        connector_factory: RemoteConnectorFactory,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
    ) -> NodeBulkCommandService:
        """Get the bulk SSH command service."""
        return NodeBulkCommandService(
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
            credential_cipher=credential_cipher,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_command_service(
        self,
        audit_service: AuditEventSink,
        connector_factory: RemoteConnectorFactory,
        node_reader: NodeConnectionReader,
        status_writer: NodeStatusWriter,
        credential_cipher: CredentialCipher,
    ) -> NodeCommandService:
        """Get the single-node SSH command service."""
        return NodeCommandService(
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
            status_writer=status_writer,
            credential_cipher=credential_cipher,
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

    @provide(scope=Scope.REQUEST)
    def get_audit_event_sink(self, audit_service: AuditService) -> AuditEventSink:
        """Bind Node use cases to the application audit port."""
        return audit_service

    @provide(scope=Scope.APP)
    def get_required_audit_writer(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> RequiredAuditWriter:
        """Get the independent writer for pre-side-effect audit intents."""
        return RequiredAuditWriter(sessionmaker)

    @provide(scope=Scope.REQUEST)
    def get_node_management_service(
        self,
        reader: NodeManagementReader,
        writer: NodeManagementWriter,
        credential_cipher: CredentialCipher,
        audit_service: AuditEventSink,
    ) -> NodeManagementService:
        """Get the node management service."""
        return NodeManagementService(
            reader=reader,
            writer=writer,
            credential_cipher=credential_cipher,
            audit_service=audit_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_command_management_service(
        self,
        reader: CommandReader,
        writer: CommandWriter,
        audit_service: AuditEventSink,
    ) -> CommandManagementService:
        """Get command management service."""
        return CommandManagementService(
            reader=reader,
            writer=writer,
            audit_service=audit_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_command_execution_service(
        self,
        audit_service: AuditEventSink,
        connector_factory: RemoteConnectorFactory,
        command_reader: CommandTemplateReader,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
    ) -> CommandExecutionService:
        """Get command execution service."""
        return CommandExecutionService(
            connector_factory=connector_factory,
            command_reader=command_reader,
            node_reader=node_reader,
            credential_cipher=credential_cipher,
            audit_service=audit_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_script_management_service(
        self,
        reader: ScriptReader,
        writer: ScriptWriter,
        audit_service: AuditEventSink,
    ) -> ScriptManagementService:
        """Get the script management service."""
        return ScriptManagementService(
            reader=reader,
            writer=writer,
            audit_service=audit_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_script_history_service(
        self,
        script_reader: ScriptReader,
        execution_reader: ScriptExecutionReader,
    ) -> ScriptHistoryService:
        """Get the script execution history service."""
        return ScriptHistoryService(
            script_reader=script_reader,
            execution_reader=execution_reader,
        )

    @provide(scope=Scope.REQUEST)
    def get_script_execution_service(
        self,
        script_reader: ScriptDefinitionReader,
        command_reader: CommandTemplateReader,
        node_reader: NodeConnectionReader,
        execution_writer: ScriptExecutionWriter,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        audit_service: AuditEventSink,
    ) -> ScriptExecutionService:
        """Get transaction-safe script execution orchestration."""
        return ScriptExecutionService(
            script_reader=script_reader,
            command_reader=command_reader,
            node_reader=node_reader,
            execution_writer=execution_writer,
            credential_cipher=credential_cipher,
            connector_factory=connector_factory,
            audit_service=audit_service,
        )

    @provide(scope=Scope.REQUEST)
    def get_schedule_management_service(
        self,
        reader: ScheduleReader,
        writer: ScheduleWriter,
        script_reader: ScriptReader,
        node_reader: NodeManagementReader,
        scheduler: JobSchedulerPort,
    ) -> ScheduleManagementService:
        """Get persistent schedule management orchestration."""
        return ScheduleManagementService(
            reader=reader,
            writer=writer,
            script_reader=script_reader,
            node_reader=node_reader,
            scheduler=scheduler,
        )

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(self, repository: APIKeyRepository) -> APIKeyService:
        """Get API key service."""
        return APIKeyService(repository=repository)

    @provide(scope=Scope.APP)
    def get_docker_command_runner(
        self,
        node_reader: NodeConnectionReader,
        runtime: DockerRuntime,
    ) -> DockerCommandRunner:
        """Compose target resolution with the Docker runtime capability."""
        return DockerCommandRunner(node_reader=node_reader, runtime=runtime)

    @provide(scope=Scope.REQUEST)
    def get_docker_container_service(
        self, runner: DockerCommandRunner, audit_service: AuditEventSink
    ) -> DockerContainerService:
        return DockerContainerService(runner, audit_service)

    @provide(scope=Scope.REQUEST)
    def get_docker_image_service(
        self, runner: DockerCommandRunner, audit_service: AuditEventSink
    ) -> DockerImageService:
        return DockerImageService(runner, audit_service)

    @provide(scope=Scope.REQUEST)
    def get_docker_resource_service(
        self, runner: DockerCommandRunner, audit_service: AuditEventSink
    ) -> DockerResourceService:
        return DockerResourceService(runner, audit_service)

    @provide(scope=Scope.REQUEST)
    def get_docker_bulk_service(self, runner: DockerCommandRunner) -> DockerBulkService:
        return DockerBulkService(runner)

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
    def get_job_scheduler(self, scheduler: ScriptScheduler) -> ApschedulerJobScheduler:
        """Adapt the managed APScheduler runtime to the application port."""
        return ApschedulerJobScheduler(scheduler)

    @provide(scope=Scope.APP)
    def get_job_scheduler_port(
        self, scheduler: ApschedulerJobScheduler
    ) -> JobSchedulerPort:
        """Bind runtime schedule operations."""
        return scheduler

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
