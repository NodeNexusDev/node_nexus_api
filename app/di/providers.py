"""DI providers for the application."""

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.lifecycle.application_startup import ApplicationStartup
from app.adapters.lifecycle.migration_runner import MigrationRunner
from app.adapters.persistence.api_key import SqlAlchemyAPIKeyGateway
from app.adapters.persistence.audit import (
    RequestAuditOutbox,
    RequiredAuditOutbox,
    SqlAlchemyAuditLogGateway,
)
from app.adapters.persistence.audit_export import SqlAlchemyAuditExporter
from app.adapters.persistence.audit_outbox_worker import AuditOutboxWorker
from app.adapters.persistence.command_history import SqlAlchemyCommandHistoryGateway
from app.adapters.persistence.command_management import SqlAlchemyCommandGateway
from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
from app.adapters.persistence.config import SqlAlchemyConfigGateway
from app.adapters.persistence.dao.command import CommandRepository
from app.adapters.persistence.dao.health import HealthRepository
from app.adapters.persistence.dao.node import NodeRepository
from app.adapters.persistence.dao.script import ScriptRepository
from app.adapters.persistence.dao.script_execution import ScriptExecutionRepository
from app.adapters.persistence.dashboard import SqlAlchemyDashboardGateway
from app.adapters.persistence.dashboard_metrics import (
    SqlAlchemyDashboardMetricsGateway,
)
from app.adapters.persistence.execution_lifecycle import (
    SqlAlchemyExecutionLifecycleGateway,
)
from app.adapters.persistence.execution_stats import SqlAlchemyExecutionStatsGateway
from app.adapters.persistence.favorite import SqlAlchemyFavoriteGateway
from app.adapters.persistence.global_search import SqlAlchemyGlobalSearchGateway
from app.adapters.persistence.note import SqlAlchemyNoteGateway
from app.adapters.persistence.node_bulk_operator import SqlAlchemyNodeBulkOperator
from app.adapters.persistence.tag_manager import SqlAlchemyTagManager
from app.adapters.persistence.node_management import (
    SqlAlchemyNodeManagementGateway,
)
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.node_status_history import (
    SqlAlchemyNodeStatusHistoryGateway,
)
from app.adapters.persistence.node_validation import SshCredentialValidator
from app.adapters.persistence.schedule import SqlAlchemyScheduleGateway
from app.adapters.persistence.script_gateway import (
    ScopedScriptDefinitionReader,
    ScopedScriptExecutionWriter,
    SqlAlchemyScriptGateway,
)
from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from app.adapters.runtime.docker import SshDockerRuntime
from app.adapters.runtime.scheduler import ApschedulerJobScheduler
from app.adapters.runtime.ssh import SSHConnectorFactory
from app.adapters.security import AesGcmCredentialCipher, Sha256APIKeyHasher
from app.application.ports.api_key import APIKeyReader, APIKeyWriter
from app.application.ports.api_key_hasher import APIKeyHasher
from app.application.ports.audit_log import AuditLogReader, AuditLogWriter
from app.application.ports.audit_outbox_controller import AuditOutboxController
from app.application.ports.audit_sink import AuditEventSink
from app.application.ports.command_history import (
    CommandHistoryReader,
    CommandHistoryWriter,
)
from app.application.ports.command_management import CommandReader, CommandWriter
from app.application.ports.command_reader import CommandTemplateReader
from app.application.ports.config_persistence import (
    ConfigurationExporter,
    ConfigurationImporter,
)
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.dashboard import DashboardReader
from app.application.ports.dashboard_metrics import DashboardMetricsReader
from app.application.ports.docker_runtime import DockerRuntime
from app.application.ports.execution_lifecycle import ExecutionLifecycleManager
from app.application.ports.execution_stats import ExecutionStatsReader
from app.application.ports.export import AuditExporter
from app.application.ports.favorite import FavoriteReader, FavoriteWriter
from app.application.ports.global_search import GlobalSearchReader
from app.application.ports.health import DatabaseHealthProbe
from app.application.ports.note import NoteReader, NoteWriter
from app.application.ports.tag_manager import TagManager
from app.application.ports.node_bulk_operator import NodeBulkOperator
from app.application.ports.node_management import (
    NodeManagementReader,
    NodeManagementWriter,
)
from app.application.ports.node_reader import NodeConnectionReader, NodeStatusWriter
from app.application.ports.node_status_history import (
    NodeStatusHistoryReader,
    NodeStatusHistoryWriter,
)
from app.application.ports.node_validation import NodeCredentialValidator
from app.application.ports.remote_command import RemoteConnectorFactory
from app.application.ports.remote_stream import RemoteStreamingConnectorFactory
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
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.api_key_management import APIKeyManagementService
from app.application.services.audit_cleanup_job import AuditCleanupJob
from app.application.services.audit_event_service import AuditEventService
from app.application.services.audit_log_service import AuditLogService
from app.application.services.bulk_command_history_service import (
    BulkCommandHistoryService,
)
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_history_service import CommandHistoryService
from app.application.services.command_management_service import CommandManagementService
from app.application.services.config_service import ConfigService
from app.application.services.dashboard_metrics_service import (
    DashboardMetricsService,
)
from app.application.services.dashboard_service import DashboardService
from app.application.services.docker.bulk_service import DockerBulkService
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.resource_service import DockerResourceService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.favorite_service import FavoriteService
from app.application.services.global_search_service import GlobalSearchService
from app.application.services.health_service import HealthService
from app.application.services.note_service import NoteService
from app.application.services.tag_management_service import TagManagementService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.application.services.node_validation_service import NodeValidationService
from app.application.services.schedule_management import (
    ScheduleManagementService,
)
from app.application.services.schedule_reconciliation import (
    ScheduleReconciliationService,
)
from app.application.services.schedule_restorer import ScheduleRestorer
from app.application.services.scheduled_script_executor import (
    ScheduledScriptExecutor,
)
from app.application.services.script_execution_service import ScriptExecutionService
from app.application.services.script_history_service import ScriptHistoryService
from app.application.services.script_management_service import ScriptManagementService
from app.application.services.streaming_command_service import StreamingCommandService
from app.core.config import Settings, get_settings


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

    @provide(scope=Scope.APP)
    def get_migration_runner(self, settings: Settings) -> MigrationRunner:
        """Get the Alembic lifecycle adapter."""
        return MigrationRunner(settings.DATABASE_URL)

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
    def get_api_key_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyAPIKeyGateway:
        """Get the short-scope API-key persistence gateway."""
        return SqlAlchemyAPIKeyGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=APIKeyReader)
    def get_api_key_reader(self, gateway: SqlAlchemyAPIKeyGateway) -> APIKeyReader:
        """Bind API-key authentication and management reads."""
        return gateway

    @provide(scope=Scope.APP, provides=APIKeyWriter)
    def get_api_key_writer(self, gateway: SqlAlchemyAPIKeyGateway) -> APIKeyWriter:
        """Bind API-key mutations and usage writes."""
        return gateway

    @provide(scope=Scope.APP)
    def get_scoped_execution_writer(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedScriptExecutionWriter:
        """Get a writer that commits execution transitions independently."""
        return ScopedScriptExecutionWriter(sessionmaker)

    @provide(scope=Scope.APP, provides=ScriptExecutionWriter)
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

    @provide(scope=Scope.APP, provides=ScriptReader)
    def get_script_reader(self, gateway: SqlAlchemyScriptGateway) -> ScriptReader:
        """Bind the script reader port."""
        return gateway

    @provide(scope=Scope.APP, provides=ScriptWriter)
    def get_script_writer(self, gateway: SqlAlchemyScriptGateway) -> ScriptWriter:
        """Bind the script writer port."""
        return gateway

    @provide(scope=Scope.APP, provides=ScriptExecutionReader)
    def get_script_execution_reader(
        self, gateway: SqlAlchemyScriptGateway
    ) -> ScriptExecutionReader:
        """Bind the execution history reader port."""
        return gateway

    @provide(scope=Scope.APP, provides=ScriptDefinitionReader)
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

    @provide(scope=Scope.APP, provides=CommandReader)
    def get_command_management_reader(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandReader:
        """Bind the command management reader port."""
        return gateway

    @provide(scope=Scope.APP, provides=CommandWriter)
    def get_command_management_writer(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandWriter:
        """Bind the command management writer port."""
        return gateway

    @provide(scope=Scope.APP, provides=CommandTemplateReader)
    def get_command_template_reader(
        self, gateway: SqlAlchemyCommandGateway
    ) -> CommandTemplateReader:
        """Bind command execution templates to the management gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_command_history_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyCommandHistoryGateway:
        """Get the short-scope command history gateway."""
        return SqlAlchemyCommandHistoryGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=CommandHistoryReader)
    def get_command_history_reader(
        self, gateway: SqlAlchemyCommandHistoryGateway
    ) -> CommandHistoryReader:
        """Bind command history reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP, provides=CommandHistoryWriter)
    def get_command_history_writer(
        self, gateway: SqlAlchemyCommandHistoryGateway
    ) -> CommandHistoryWriter:
        """Bind command history writes to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_scoped_node_reader(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> ScopedNodeConnectionReader:
        """Get a node reader that owns a short session per operation."""
        return ScopedNodeConnectionReader(sessionmaker)

    @provide(scope=Scope.APP, provides=NodeConnectionReader)
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

    @provide(scope=Scope.APP, provides=NodeManagementReader)
    def get_node_management_reader(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeManagementReader:
        """Bind the node management reader port."""
        return gateway

    @provide(scope=Scope.APP, provides=NodeManagementWriter)
    def get_node_management_writer(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeManagementWriter:
        """Bind the node management writer port."""
        return gateway

    @provide(scope=Scope.APP, provides=NodeStatusWriter)
    def get_node_status_writer(
        self, gateway: SqlAlchemyNodeManagementGateway
    ) -> NodeStatusWriter:
        """Bind the node status writer port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_node_status_history_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyNodeStatusHistoryGateway:
        """Get the short-scope node status history gateway."""
        return SqlAlchemyNodeStatusHistoryGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=NodeStatusHistoryReader)
    def get_node_status_history_reader(
        self, gateway: SqlAlchemyNodeStatusHistoryGateway
    ) -> NodeStatusHistoryReader:
        """Bind the node status history reader port."""
        return gateway

    @provide(scope=Scope.APP, provides=NodeStatusHistoryWriter)
    def get_node_status_history_writer(
        self, gateway: SqlAlchemyNodeStatusHistoryGateway
    ) -> NodeStatusHistoryWriter:
        """Bind the node status history writer port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_node_bulk_operator(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyNodeBulkOperator:
        """Get the short-scope bulk node operator."""
        return SqlAlchemyNodeBulkOperator(sessionmaker)

    @provide(scope=Scope.APP, provides=NodeBulkOperator)
    def get_node_bulk_operator_port(
        self, gateway: SqlAlchemyNodeBulkOperator
    ) -> NodeBulkOperator:
        """Bind the bulk node operator port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_execution_lifecycle_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyExecutionLifecycleGateway:
        """Get the short-scope execution lifecycle gateway."""
        return SqlAlchemyExecutionLifecycleGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=ExecutionLifecycleManager)
    def get_execution_lifecycle_manager(
        self, gateway: SqlAlchemyExecutionLifecycleGateway
    ) -> ExecutionLifecycleManager:
        """Bind the execution lifecycle manager port."""
        return gateway

    @provide(scope=Scope.APP)
    def get_schedule_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyScheduleGateway:
        """Get the short-scope persistent schedule gateway."""
        return SqlAlchemyScheduleGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=ScheduleReader)
    def get_schedule_reader(self, gateway: SqlAlchemyScheduleGateway) -> ScheduleReader:
        """Bind persistent schedule reads."""
        return gateway

    @provide(scope=Scope.APP, provides=ScheduleWriter)
    def get_schedule_writer(self, gateway: SqlAlchemyScheduleGateway) -> ScheduleWriter:
        """Bind persistent schedule writes."""
        return gateway

    @provide(scope=Scope.REQUEST)
    def get_node_repository(self, session: AsyncSession) -> NodeRepository:
        """Get node repository."""
        return NodeRepository(session)

    @provide(scope=Scope.APP)
    def get_audit_log_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyAuditLogGateway:
        """Get the persistent audit-log gateway."""
        return SqlAlchemyAuditLogGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=AuditLogReader)
    def get_audit_log_reader(
        self, gateway: SqlAlchemyAuditLogGateway
    ) -> AuditLogReader:
        """Bind audit-log queries."""
        return gateway

    @provide(scope=Scope.APP, provides=AuditLogWriter)
    def get_audit_log_writer(
        self, gateway: SqlAlchemyAuditLogGateway
    ) -> AuditLogWriter:
        """Bind audit-log retention writes."""
        return gateway

    @provide(scope=Scope.APP)
    def get_dashboard_gateway(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        node_reader: NodeConnectionReader,
        runtime: DockerRuntime,
    ) -> SqlAlchemyDashboardGateway:
        """Get the dashboard aggregation gateway."""
        return SqlAlchemyDashboardGateway(
            sessionmaker, node_reader=node_reader, runtime=runtime
        )

    @provide(scope=Scope.APP, provides=DashboardReader)
    def get_dashboard_reader(
        self, gateway: SqlAlchemyDashboardGateway
    ) -> DashboardReader:
        """Bind dashboard reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_dashboard_metrics_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyDashboardMetricsGateway:
        """Get the short-scope dashboard metrics gateway."""
        return SqlAlchemyDashboardMetricsGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=DashboardMetricsReader)
    def get_dashboard_metrics_reader(
        self, gateway: SqlAlchemyDashboardMetricsGateway
    ) -> DashboardMetricsReader:
        """Bind dashboard metrics reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.REQUEST, provides=AuditExporter)
    def get_audit_exporter(
        self, session: AsyncSession
    ) -> AuditExporter:
        """Bind audit export to the persistence adapter."""
        return SqlAlchemyAuditExporter(session)

    @provide(scope=Scope.REQUEST, provides=TagManager)
    def get_tag_manager(
        self, session: AsyncSession
    ) -> TagManager:
        """Bind tag management to the persistence adapter."""
        return SqlAlchemyTagManager(session)

    @provide(scope=Scope.REQUEST, provides=FavoriteReader)
    def get_favorite_reader(
        self, session: AsyncSession
    ) -> FavoriteReader:
        """Bind favorite reader to the persistence adapter."""
        return SqlAlchemyFavoriteGateway(session)

    @provide(scope=Scope.REQUEST, provides=FavoriteWriter)
    def get_favorite_writer(
        self, session: AsyncSession
    ) -> FavoriteWriter:
        """Bind favorite writer to the persistence adapter."""
        return SqlAlchemyFavoriteGateway(session)

    @provide(scope=Scope.REQUEST, provides=NoteReader)
    def get_note_reader(
        self, session: AsyncSession
    ) -> NoteReader:
        """Bind note reader to the persistence adapter."""
        return SqlAlchemyNoteGateway(session)

    @provide(scope=Scope.REQUEST, provides=NoteWriter)
    def get_note_writer(
        self, session: AsyncSession
    ) -> NoteWriter:
        """Bind note writer to the persistence adapter."""
        return SqlAlchemyNoteGateway(session)

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
    def get_health_repository(self, session: AsyncSession) -> HealthRepository:
        """Get health check repository."""
        return HealthRepository(session)

    @provide(scope=Scope.APP)
    def get_config_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyConfigGateway:
        """Get the coordinated configuration persistence gateway."""
        return SqlAlchemyConfigGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=ConfigurationExporter)
    def get_configuration_exporter(
        self, gateway: SqlAlchemyConfigGateway
    ) -> ConfigurationExporter:
        return gateway

    @provide(scope=Scope.APP, provides=ConfigurationImporter)
    def get_configuration_importer(
        self, gateway: SqlAlchemyConfigGateway
    ) -> ConfigurationImporter:
        return gateway

    @provide(scope=Scope.REQUEST, provides=DatabaseHealthProbe)
    def get_database_health_probe(
        self, repository: HealthRepository
    ) -> DatabaseHealthProbe:
        """Bind database readiness checks to the persistence adapter."""
        return repository

    @provide(scope=Scope.APP)
    def get_execution_stats_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyExecutionStatsGateway:
        """Get the short-scope execution statistics gateway."""
        return SqlAlchemyExecutionStatsGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=ExecutionStatsReader)
    def get_execution_stats_reader(
        self, gateway: SqlAlchemyExecutionStatsGateway
    ) -> ExecutionStatsReader:
        """Bind execution statistics reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_global_search_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyGlobalSearchGateway:
        """Get the short-scope global search gateway."""
        return SqlAlchemyGlobalSearchGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=GlobalSearchReader)
    def get_global_search_reader(
        self, gateway: SqlAlchemyGlobalSearchGateway
    ) -> GlobalSearchReader:
        """Bind global search reads to the persistence gateway."""
        return gateway


class ConnectorProvider(Provider):
    """Connector providers."""

    @provide(scope=Scope.APP)
    def get_ssh_connector_factory(self, settings: Settings) -> SSHConnectorFactory:
        """Get SSH connector factory."""
        return SSHConnectorFactory(
            known_hosts_path=settings.SSH_KNOWN_HOSTS_PATH,
            strict_host_key_checking=settings.SSH_STRICT_HOST_KEY_CHECKING,
        )

    @provide(scope=Scope.APP, provides=RemoteConnectorFactory)
    def get_remote_connector_factory(
        self, factory: SSHConnectorFactory
    ) -> RemoteConnectorFactory:
        """Bind remote command sessions to the SSH adapter."""
        return factory

    @provide(scope=Scope.APP, provides=RemoteStreamingConnectorFactory)
    def get_remote_streaming_connector_factory(
        self, factory: SSHConnectorFactory
    ) -> RemoteStreamingConnectorFactory:
        """Bind SSH streaming to its application port."""
        return factory

    @provide(scope=Scope.APP, provides=CredentialCipher)
    def get_credential_cipher(self) -> CredentialCipher:
        """Bind credential protection to the configured AES-GCM adapter."""
        return AesGcmCredentialCipher()

    @provide(scope=Scope.APP, provides=APIKeyHasher)
    def get_api_key_hasher(self) -> APIKeyHasher:
        """Bind API-key lookup hashing to the SHA-256 adapter."""
        return Sha256APIKeyHasher()

    @provide(scope=Scope.APP, provides=DockerRuntime)
    def get_docker_runtime(
        self,
        connector_factory: RemoteConnectorFactory,
        credential_cipher: CredentialCipher,
    ) -> DockerRuntime:
        """Bind Docker CLI execution to the SSH runtime adapter."""
        return SshDockerRuntime(connector_factory, credential_cipher)

    @provide(scope=Scope.APP, provides=NodeCredentialValidator)
    def get_node_credential_validator(
        self,
        connector_factory: RemoteConnectorFactory,
    ) -> NodeCredentialValidator:
        """Bind credential validation to the SSH adapter."""
        return SshCredentialValidator(connector_factory)


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
        history_writer: CommandHistoryWriter,
    ) -> NodeBulkCommandService:
        """Get the bulk SSH command service."""
        return NodeBulkCommandService(
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
            credential_cipher=credential_cipher,
            history_writer=history_writer,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_command_service(
        self,
        audit_service: AuditEventSink,
        connector_factory: RemoteConnectorFactory,
        node_reader: NodeConnectionReader,
        status_writer: NodeStatusWriter,
        credential_cipher: CredentialCipher,
        history_writer: CommandHistoryWriter,
        status_history_writer: NodeStatusHistoryWriter,
    ) -> NodeCommandService:
        """Get the single-node SSH command service."""
        return NodeCommandService(
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
            status_writer=status_writer,
            credential_cipher=credential_cipher,
            history_writer=history_writer,
            status_history_writer=status_history_writer,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_status_history_service(
        self,
        reader: NodeStatusHistoryReader,
        writer: NodeStatusHistoryWriter,
    ) -> NodeStatusHistoryService:
        """Get the node status history service."""
        return NodeStatusHistoryService(reader=reader, writer=writer)

    @provide(scope=Scope.APP)
    def get_streaming_command_service(
        self,
        node_reader: NodeConnectionReader,
        connector_factory: RemoteStreamingConnectorFactory,
        credential_cipher: CredentialCipher,
    ) -> StreamingCommandService:
        """Get WebSocket streaming orchestration service."""
        return StreamingCommandService(
            node_reader,
            connector_factory,
            credential_cipher,
        )

    @provide(scope=Scope.REQUEST)
    def get_audit_event_service(
        self,
        optional_outbox: RequestAuditOutbox,
        required_outbox: RequiredAuditOutbox,
    ) -> AuditEventService:
        """Get audit event use cases."""
        return AuditEventService(
            optional_outbox=optional_outbox,
            required_outbox=required_outbox,
        )

    @provide(scope=Scope.REQUEST, provides=AuditEventSink)
    def get_audit_event_sink(self, audit_service: AuditEventService) -> AuditEventSink:
        """Bind Node use cases to the application audit port."""
        return audit_service

    @provide(scope=Scope.REQUEST)
    def get_request_audit_outbox(self, session: AsyncSession) -> RequestAuditOutbox:
        """Get the request-transaction audit outbox."""
        return RequestAuditOutbox(session)

    @provide(scope=Scope.APP)
    def get_required_audit_outbox(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> RequiredAuditOutbox:
        """Get the independent outbox for pre-side-effect audit intents."""
        return RequiredAuditOutbox(sessionmaker)

    @provide(scope=Scope.APP)
    def get_audit_log_service(
        self,
        reader: AuditLogReader,
        writer: AuditLogWriter,
    ) -> AuditLogService:
        """Get audit-log query and retention use cases."""
        return AuditLogService(reader, writer)

    @provide(scope=Scope.APP)
    def get_command_history_service(
        self,
        reader: CommandHistoryReader,
    ) -> CommandHistoryService:
        """Get command execution history query use cases."""
        return CommandHistoryService(reader)

    @provide(scope=Scope.APP)
    def get_bulk_command_history_service(
        self,
        reader: CommandHistoryReader,
    ) -> BulkCommandHistoryService:
        """Get bulk command batch history query use cases."""
        return BulkCommandHistoryService(reader)

    @provide(scope=Scope.APP)
    def get_audit_cleanup_job(
        self,
        writer: AuditLogWriter,
        settings: Settings,
    ) -> AuditCleanupJob:
        """Get the startup audit-retention job."""
        return AuditCleanupJob(writer, settings.AUDIT_LOG_RETENTION_DAYS)

    @provide(scope=Scope.REQUEST)
    def get_node_management_service(
        self,
        reader: NodeManagementReader,
        writer: NodeManagementWriter,
        credential_cipher: CredentialCipher,
        audit_service: AuditEventSink,
        status_history_writer: NodeStatusHistoryWriter,
    ) -> NodeManagementService:
        """Get the node management service."""
        return NodeManagementService(
            reader=reader,
            writer=writer,
            credential_cipher=credential_cipher,
            audit_service=audit_service,
            status_history_writer=status_history_writer,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_bulk_operation_service(
        self,
        operator: NodeBulkOperator,
    ) -> NodeBulkOperationService:
        """Get the bulk node operation service."""
        return NodeBulkOperationService(operator=operator)

    @provide(scope=Scope.REQUEST)
    def get_execution_lifecycle_service(
        self,
        manager: ExecutionLifecycleManager,
        command_history_reader: CommandHistoryReader,
    ) -> ExecutionLifecycleService:
        """Get the execution lifecycle service."""
        return ExecutionLifecycleService(
            manager=manager,
            command_history_reader=command_history_reader,
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
        history_writer: CommandHistoryWriter,
    ) -> CommandExecutionService:
        """Get command execution service."""
        return CommandExecutionService(
            connector_factory=connector_factory,
            command_reader=command_reader,
            node_reader=node_reader,
            credential_cipher=credential_cipher,
            audit_service=audit_service,
            history_writer=history_writer,
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

    @provide(scope=Scope.APP)
    def get_api_key_authentication_service(
        self,
        reader: APIKeyReader,
        writer: APIKeyWriter,
        hasher: APIKeyHasher,
    ) -> APIKeyAuthenticationService:
        """Get API-key authentication query use case."""
        return APIKeyAuthenticationService(reader, writer, hasher)

    @provide(scope=Scope.APP)
    def get_api_key_management_service(
        self,
        reader: APIKeyReader,
        writer: APIKeyWriter,
        hasher: APIKeyHasher,
    ) -> APIKeyManagementService:
        """Get API-key management use cases."""
        return APIKeyManagementService(reader, writer, hasher)

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
        repository: DatabaseHealthProbe,
        scheduler: JobSchedulerPort,
        settings: Settings,
    ) -> HealthService:
        """Get health check service."""
        return HealthService(
            repository=repository,
            scheduler=scheduler,
            scheduler_enabled=settings.SCHEDULER_ENABLED,
        )

    @provide(scope=Scope.APP)
    def get_config_service(
        self,
        exporter: ConfigurationExporter,
        importer: ConfigurationImporter,
    ) -> ConfigService:
        """Get configuration import/export service."""
        return ConfigService(exporter=exporter, importer=importer)

    @provide(scope=Scope.APP)
    def get_dashboard_service(
        self,
        reader: DashboardReader,
    ) -> DashboardService:
        """Get dashboard overview service."""
        return DashboardService(reader=reader)

    @provide(scope=Scope.APP)
    def get_node_validation_service(
        self,
        validator: NodeCredentialValidator,
    ) -> NodeValidationService:
        """Get node credential validation service."""
        return NodeValidationService(validator=validator)

    @provide(scope=Scope.REQUEST)
    def get_execution_stats_service(
        self,
        reader: ExecutionStatsReader,
    ) -> ExecutionStatsService:
        """Get execution statistics service."""
        return ExecutionStatsService(reader=reader)

    @provide(scope=Scope.REQUEST)
    def get_global_search_service(
        self,
        reader: GlobalSearchReader,
    ) -> GlobalSearchService:
        """Get global search service."""
        return GlobalSearchService(reader=reader)

    @provide(scope=Scope.REQUEST)
    def get_dashboard_metrics_service(
        self,
        reader: DashboardMetricsReader,
    ) -> DashboardMetricsService:
        """Get dashboard metrics service."""
        return DashboardMetricsService(reader=reader)

    @provide(scope=Scope.REQUEST)
    def get_tag_management_service(
        self,
        tag_manager: TagManager,
    ) -> TagManagementService:
        """Get tag management service."""
        return TagManagementService(tag_manager=tag_manager)

    @provide(scope=Scope.REQUEST)
    def get_favorite_service(
        self,
        reader: FavoriteReader,
        writer: FavoriteWriter,
    ) -> FavoriteService:
        """Get favorite service."""
        return FavoriteService(reader=reader, writer=writer)

    @provide(scope=Scope.REQUEST)
    def get_note_service(
        self,
        reader: NoteReader,
        writer: NoteWriter,
    ) -> NoteService:
        """Get note service."""
        return NoteService(reader=reader, writer=writer)


class ConfigProvider(Provider):
    """Configuration provider."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Get application settings."""
        return get_settings()


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

    @provide(scope=Scope.APP)
    async def get_script_scheduler(
        self, engine: AsyncEngine, settings: Settings
    ) -> AsyncIterable[ApschedulerRuntime]:
        """Start and finalize the application-scoped script scheduler."""
        scheduler = ApschedulerRuntime()
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
        )


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
