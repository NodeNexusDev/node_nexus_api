"""DI providers for the application."""

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.connectors.ssh import SSHConnectorFactory
from app.repositories.api_key_repo import APIKeyRepository
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.command_repo import CommandRepository
from app.repositories.node_repo import NodeRepository
from app.repositories.script_execution_repo import ScriptExecutionRepository
from app.repositories.script_repo import ScriptRepository
from app.services.api_key_service import APIKeyService
from app.services.audit_service import AuditService
from app.services.command_service import CommandService
from app.services.node_service import NodeService
from app.services.script_service import ScriptService


class DbProvider(Provider):
    """Database session provider."""

    @provide(scope=Scope.APP)
    def get_sessionmaker(self, settings: Settings) -> async_sessionmaker[AsyncSession]:
        """Get a session maker."""
        engine = create_async_engine(settings.DATABASE_URL)
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
    def get_api_key_repository(self, session: AsyncSession) -> APIKeyRepository:
        """Get API key repository."""
        return APIKeyRepository(session)


class ConnectorProvider(Provider):
    """Connector providers."""

    @provide(scope=Scope.APP)
    def get_ssh_connector_factory(self) -> SSHConnectorFactory:
        """Get SSH connector factory."""
        return SSHConnectorFactory()


class ServiceProvider(Provider):
    """Service providers."""

    @provide(scope=Scope.REQUEST)
    def get_audit_service(self, repository: AuditLogRepository) -> AuditService:
        """Get audit service."""
        return AuditService(repository=repository)

    @provide(scope=Scope.REQUEST)
    def get_node_service(
        self,
        repository: NodeRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
    ) -> NodeService:
        """Get node service."""
        return NodeService(
            repository=repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
        )

    @provide(scope=Scope.REQUEST)
    def get_command_service(
        self,
        repository: CommandRepository,
        node_repository: NodeRepository,
        audit_service: AuditService,
        connector_factory: SSHConnectorFactory,
    ) -> CommandService:
        """Get command service."""
        return CommandService(
            repository=repository,
            node_repository=node_repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
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
    ) -> ScriptService:
        """Get script service."""
        return ScriptService(
            repository=repository,
            command_repository=command_repository,
            node_repository=node_repository,
            execution_repository=execution_repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
        )

    @provide(scope=Scope.REQUEST)
    def get_api_key_service(self, repository: APIKeyRepository) -> APIKeyService:
        """Get API key service."""
        return APIKeyService(repository=repository)


class ConfigProvider(Provider):
    """Configuration provider."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Get application settings."""
        return get_settings()


class AppProvider(
    ConfigProvider, DbProvider, RepositoryProvider, ConnectorProvider, ServiceProvider
):
    """Main application provider."""

    pass
