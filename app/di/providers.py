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
from app.services.api_key_service import APIKeyService
from app.services.audit_service import AuditService
from app.services.command_service import CommandService
from app.services.config_service import ConfigService
from app.services.docker_service import DockerService
from app.services.health_service import HealthService
from app.services.node_service import NodeService
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
    def get_ssh_connector_factory(self) -> SSHConnectorFactory:
        """Get SSH connector factory."""
        return SSHConnectorFactory()


class ServiceProvider(Provider):
    """Service providers."""

    @provide(scope=Scope.REQUEST)
    def get_streaming_command_service(
        self,
        node_reader: ScopedNodeConnectionReader,
        connector_factory: SSHConnectorFactory,
    ) -> StreamingCommandService:
        """Get WebSocket streaming orchestration service."""
        return StreamingCommandService(node_reader, connector_factory)

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
        node_reader: ScopedNodeConnectionReader,
    ) -> NodeService:
        """Get node service."""
        return NodeService(
            repository=repository,
            audit_service=audit_service,
            connector_factory=connector_factory,
            node_reader=node_reader,
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
    def get_health_service(self, repository: HealthRepository) -> HealthService:
        """Get health check service."""
        return HealthService(repository=repository)

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


class ConfigProvider(Provider):
    """Configuration provider."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Get application settings."""
        return get_settings()


class SchedulerProvider(Provider):
    """Scheduler providers."""

    @provide(scope=Scope.APP)
    async def get_script_scheduler(self) -> AsyncIterable[ScriptScheduler]:
        """Start and finalize the application-scoped script scheduler."""
        scheduler = ScriptScheduler()
        await scheduler.start()
        try:
            yield scheduler
        finally:
            await scheduler.stop()


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
