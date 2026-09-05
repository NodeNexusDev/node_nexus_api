# ruff: noqa: I001
"""DI providers for the application."""

from __future__ import annotations


from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.adapters.persistence.api_key import SqlAlchemyAPIKeyGateway
from app.adapters.persistence.audit import (
    SqlAlchemyAuditLogGateway,
)
from app.adapters.persistence.audit_export import SqlAlchemyAuditExporter
from app.adapters.persistence.command_history import SqlAlchemyCommandHistoryGateway
from app.adapters.persistence.command_management import SqlAlchemyCommandGateway
from app.adapters.persistence.command_reader import ScopedCommandTemplateReader
from app.adapters.persistence.compose import SqlAlchemyComposeGateway
from app.adapters.persistence.config import SqlAlchemyConfigGateway
from app.adapters.persistence.dao.health import HealthRepository
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
from app.application.ports.api_key import APIKeyReader, APIKeyWriter
from app.application.ports.audit_log import AuditLogReader, AuditLogWriter
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
from app.application.ports.execution_lifecycle import ExecutionLifecycleManager
from app.application.ports.execution_stats import ExecutionStatsReader
from app.application.ports.export import AuditExporter
from app.application.ports.favorite import FavoriteReader, FavoriteWriter
from app.application.ports.global_search import GlobalSearchReader
from app.application.ports.health import DatabaseHealthProbe
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
from app.application.ports.password_hasher import PasswordHasher
from app.application.ports.refresh_token_persistence import (
    RefreshTokenReader,
    RefreshTokenWriter,
)
from app.application.ports.schedule import (
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

    @provide(scope=Scope.REQUEST, provides=AuditExporter)
    def get_audit_exporter(self, session: AsyncSession) -> AuditExporter:
        """Bind audit export to the persistence adapter."""
        return SqlAlchemyAuditExporter(session)

    @provide(scope=Scope.REQUEST, provides=FavoriteReader)
    def get_favorite_reader(self, session: AsyncSession) -> FavoriteReader:
        """Bind favorite reader to the persistence adapter."""
        return SqlAlchemyFavoriteGateway(session)

    @provide(scope=Scope.REQUEST, provides=FavoriteWriter)
    def get_favorite_writer(self, session: AsyncSession) -> FavoriteWriter:
        """Bind favorite writer to the persistence adapter."""
        return SqlAlchemyFavoriteGateway(session)

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

    @provide(scope=Scope.APP)
    def get_user_gateway(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        password_hasher: PasswordHasher,
    ) -> SqlAlchemyUserGateway:
        """Get the user persistence gateway."""
        return SqlAlchemyUserGateway(sessionmaker, password_hasher)

    @provide(scope=Scope.APP, provides=UserReader)
    def get_user_reader(self, gateway: SqlAlchemyUserGateway) -> UserReader:
        """Bind user reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP, provides=UserWriter)
    def get_user_writer(self, gateway: SqlAlchemyUserGateway) -> UserWriter:
        """Bind user writes to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_refresh_token_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyRefreshTokenGateway:
        """Get the refresh token persistence gateway."""
        return SqlAlchemyRefreshTokenGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=RefreshTokenReader)
    def get_refresh_token_reader(
        self, gateway: SqlAlchemyRefreshTokenGateway
    ) -> RefreshTokenReader:
        """Bind refresh token reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP, provides=RefreshTokenWriter)
    def get_refresh_token_writer(
        self, gateway: SqlAlchemyRefreshTokenGateway
    ) -> RefreshTokenWriter:
        """Bind refresh token writes to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP)
    def get_compose_gateway(
        self, sessionmaker: async_sessionmaker[AsyncSession]
    ) -> SqlAlchemyComposeGateway:
        """Get the short-scope compose persistence gateway."""
        return SqlAlchemyComposeGateway(sessionmaker)

    @provide(scope=Scope.APP, provides=ComposeReader)
    def get_compose_reader(self, gateway: SqlAlchemyComposeGateway) -> ComposeReader:
        """Bind compose reads to the persistence gateway."""
        return gateway

    @provide(scope=Scope.APP, provides=ComposeWriter)
    def get_compose_writer(self, gateway: SqlAlchemyComposeGateway) -> ComposeWriter:
        """Bind compose writes to the persistence gateway."""
        return gateway
