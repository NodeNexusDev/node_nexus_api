# ruff: noqa: F401, I001
"""DI providers for the application."""

from __future__ import annotations

from collections.abc import AsyncIterable
from typing import cast

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

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
from app.adapters.persistence.compose import SqlAlchemyComposeGateway
from app.adapters.persistence.config import SqlAlchemyConfigGateway
from app.adapters.persistence.dao.command import CommandRepository
from app.adapters.persistence.dao.health import HealthRepository
from app.adapters.persistence.dao.node import NodeRepository
from app.adapters.persistence.dao.script import ScriptRepository
from app.adapters.persistence.dao.script_execution import ScriptExecutionRepository
from app.adapters.persistence.execution_lifecycle import (
    SqlAlchemyExecutionLifecycleGateway,
)
from app.adapters.persistence.execution_stats import SqlAlchemyExecutionStatsGateway
from app.adapters.persistence.favorite import SqlAlchemyFavoriteGateway
from app.adapters.persistence.global_search import SqlAlchemyGlobalSearchGateway
from app.adapters.persistence.node_bulk_operator import SqlAlchemyNodeBulkOperator
from app.adapters.persistence.node_management import (
    SqlAlchemyNodeManagementGateway,
)
from app.adapters.persistence.node_reader import ScopedNodeConnectionReader
from app.adapters.persistence.node_status_history import (
    SqlAlchemyNodeStatusHistoryGateway,
)
from app.adapters.persistence.schedule import SqlAlchemyScheduleGateway
from app.adapters.persistence.script_gateway import (
    ScopedScriptDefinitionReader,
    ScopedScriptExecutionWriter,
    SqlAlchemyScriptGateway,
)
from app.adapters.persistence.user import (
    SqlAlchemyRefreshTokenGateway,
    SqlAlchemyUserGateway,
)
from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from app.adapters.runtime.docker import SshDockerRuntime
from app.adapters.runtime.known_hosts import FileKnownHostsManager
from app.adapters.runtime.node_validation import SshCredentialValidator
from app.adapters.runtime.scheduler import ApschedulerJobScheduler
from app.adapters.runtime.ssh import SSHConnectorFactory
from app.adapters.security import AesGcmCredentialCipher, HmacSha256APIKeyHasher
from app.adapters.security.jwt_handler import JWTHandlerAdapter
from app.adapters.security.password_hasher import PasswordHasherAdapter
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
from app.application.ports.compose import ComposeReader, ComposeWriter
from app.application.ports.config_persistence import (
    ConfigurationExporter,
    ConfigurationImporter,
)
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.docker_runtime import DockerRuntime
from app.application.ports.execution_lifecycle import ExecutionLifecycleManager
from app.application.ports.execution_stats import ExecutionStatsReader
from app.application.ports.export import AuditExporter
from app.application.ports.favorite import FavoriteReader, FavoriteWriter
from app.application.ports.global_search import GlobalSearchReader
from app.application.ports.health import DatabaseHealthProbe
from app.application.ports.jwt_handler import JWTHandler
from app.application.ports.known_hosts import KnownHostsManager
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
from app.application.ports.password_hasher import PasswordHasher
from app.application.ports.refresh_token_persistence import (
    RefreshTokenReader,
    RefreshTokenWriter,
)
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
from app.application.ports.user_persistence import UserReader, UserWriter
from app.application.services.api_key_authentication import (
    APIKeyAuthenticationService,
)
from app.application.services.api_key_management import APIKeyManagementService
from app.application.services.audit_cleanup_job import AuditCleanupJob
from app.application.services.audit_event_service import AuditEventService
from app.application.services.audit_log_service import AuditLogService
from app.application.services.auth_service import AuthService
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_management_service import CommandManagementService
from app.application.services.compose_service import ComposeService
from app.application.services.config_service import ConfigService
from app.application.services.docker.bulk_service import DockerBulkService
from app.application.services.docker.command_runner import DockerCommandRunner
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.resource_service import DockerResourceService
from app.application.services.docker.system_service import DockerSystemService
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
from app.application.services.favorite_service import FavoriteService
from app.application.services.global_search_service import GlobalSearchService
from app.application.services.health_service import HealthService
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_command_service import NodeCommandService
from app.application.services.node_host_key_service import NodeHostKeyService
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
from app.application.services.template_pack_service import TemplatePackService
from app.application.services.template_registry_service import TemplateRegistryService
from app.application.services.user_service import UserService
from app.core.config import Settings, get_settings


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
    def get_execution_history_service(
        self,
        reader: CommandHistoryReader,
    ) -> ExecutionHistoryService:
        """Get unified command execution history query service."""
        return ExecutionHistoryService(reader)

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
        known_hosts: KnownHostsManager,
    ) -> NodeManagementService:
        """Get the node management service."""
        return NodeManagementService(
            reader=reader,
            writer=writer,
            credential_cipher=credential_cipher,
            audit_service=audit_service,
            status_history_writer=status_history_writer,
            known_hosts=known_hosts,
        )

    @provide(scope=Scope.REQUEST)
    def get_node_bulk_operation_service(
        self,
        operator: NodeBulkOperator,
        audit_service: AuditEventSink,
        node_reader: NodeConnectionReader,
        status_writer: NodeStatusWriter,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
        status_history_writer: NodeStatusHistoryWriter,
    ) -> NodeBulkOperationService:
        """Get the bulk node operation service."""
        return NodeBulkOperationService(
            operator=operator,
            audit_service=audit_service,
            node_reader=node_reader,
            status_writer=status_writer,
            credential_cipher=credential_cipher,
            connector_factory=connector_factory,
            status_history_writer=status_history_writer,
        )

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
    def get_docker_system_service(
        self, runner: DockerCommandRunner, audit_service: AuditEventSink
    ) -> DockerSystemService:
        return DockerSystemService(runner, audit_service)

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
    def get_node_validation_service(
        self,
        validator: NodeCredentialValidator,
    ) -> NodeValidationService:
        """Get node credential validation service."""
        return NodeValidationService(validator=validator)

    @provide(scope=Scope.REQUEST)
    def get_node_host_key_service(
        self,
        reader: NodeManagementReader,
        known_hosts: KnownHostsManager,
    ) -> NodeHostKeyService:
        """Get host-key refresh service."""
        return NodeHostKeyService(reader=reader, known_hosts=known_hosts)

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
    def get_favorite_service(
        self,
        reader: FavoriteReader,
        writer: FavoriteWriter,
    ) -> FavoriteService:
        """Get favorite service."""
        return FavoriteService(reader=reader, writer=writer)

    @provide(scope=Scope.REQUEST)
    def get_auth_service(
        self,
        user_reader: UserReader,
        refresh_reader: RefreshTokenReader,
        refresh_writer: RefreshTokenWriter,
        jwt_handler: JWTHandler,
        password_hasher: PasswordHasher,
        settings: Settings,
    ) -> AuthService:
        """Get authentication service."""
        return AuthService(
            user_reader=user_reader,
            refresh_reader=refresh_reader,
            refresh_writer=refresh_writer,
            jwt_handler=jwt_handler,
            password_hasher=password_hasher,
            refresh_token_expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        )

    @provide(scope=Scope.REQUEST)
    def get_user_service(
        self,
        reader: UserReader,
        writer: UserWriter,
    ) -> UserService:
        """Get user management service."""
        return UserService(reader=reader, writer=writer)

    @provide(scope=Scope.REQUEST)
    def get_template_registry_service(self) -> TemplateRegistryService:
        """Get template registry service (in-memory stub)."""
        return TemplateRegistryService()

    @provide(scope=Scope.REQUEST)
    def get_template_pack_service(self) -> TemplatePackService:
        """Get template pack service (in-memory stub with assets)."""
        return TemplatePackService()

    @provide(scope=Scope.REQUEST)
    def get_compose_service(
        self,
        reader: ComposeReader,
        writer: ComposeWriter,
        runner: DockerCommandRunner,
    ) -> ComposeService:
        """Get compose project orchestration."""
        return ComposeService(reader=reader, writer=writer, runner=runner)
