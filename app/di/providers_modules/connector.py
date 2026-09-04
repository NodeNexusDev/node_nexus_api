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


class ConnectorProvider(Provider):
    """Connector providers."""

    @provide(scope=Scope.APP)
    def get_ssh_connector_factory(self, settings: Settings) -> SSHConnectorFactory:
        """Get SSH connector factory."""
        return SSHConnectorFactory(
            known_hosts_path=settings.SSH_KNOWN_HOSTS_PATH,
            strict_host_key_checking=settings.SSH_STRICT_HOST_KEY_CHECKING,
        )

    @provide(scope=Scope.APP, provides=KnownHostsManager)
    def get_known_hosts_manager(self, settings: Settings) -> KnownHostsManager:
        """Get file-based known_hosts manager."""
        return cast(KnownHostsManager, FileKnownHostsManager(settings))

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
        """Bind API-key lookup hashing to the HMAC-SHA-256 adapter."""
        return HmacSha256APIKeyHasher()

    @provide(scope=Scope.APP, provides=JWTHandler)
    def get_jwt_handler(self) -> JWTHandler:
        """Bind JWT operations to the PyJWT adapter."""
        return JWTHandlerAdapter()

    @provide(scope=Scope.APP, provides=PasswordHasher)
    def get_password_hasher(self) -> PasswordHasher:
        """Bind password hashing to the bcrypt adapter."""
        return PasswordHasherAdapter()

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
        known_hosts: KnownHostsManager,
    ) -> NodeCredentialValidator:
        """Bind credential validation to the SSH adapter."""
        return SshCredentialValidator(connector_factory, known_hosts)
