"""DI providers for the application."""

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.node_repo import NodeRepository
from app.services.audit_service import AuditService
from app.services.node_service import NodeService


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


class ServiceProvider(Provider):
    """Service providers."""

    @provide(scope=Scope.REQUEST)
    def get_audit_service(self, repository: AuditLogRepository) -> AuditService:
        """Get audit service."""
        return AuditService(repository=repository)

    @provide(scope=Scope.REQUEST)
    def get_node_service(
        self, repository: NodeRepository, audit_service: AuditService
    ) -> NodeService:
        """Get node service."""
        return NodeService(repository=repository, audit_service=audit_service)


class ConfigProvider(Provider):
    """Configuration provider."""

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        """Get application settings."""
        return Settings()  # type: ignore[call-arg]


class AppProvider(ConfigProvider, DbProvider, RepositoryProvider, ServiceProvider):
    """Main application provider."""

    pass
