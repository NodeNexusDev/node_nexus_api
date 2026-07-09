"""DI providers for the application."""

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.node_repo import NodeRepository
from app.services.node_service import NodeService


class DbProvider(Provider):
    """Database session provider."""

    @provide(scope=Scope.REQUEST)
    async def get_session(self, sessionmaker: async_sessionmaker) -> AsyncIterable[AsyncSession]:
        """Get a database session."""
        async with sessionmaker() as session:
            yield session


class RepositoryProvider(Provider):
    """Repository providers."""

    @provide
    def get_node_repository(self, session: AsyncSession) -> NodeRepository:
        """Get node repository."""
        return NodeRepository(session)


class ServiceProvider(Provider):
    """Service providers."""

    @provide
    def get_node_service(self, repository: NodeRepository) -> NodeService:
        """Get node service."""
        return NodeService(repository=repository)


class AppProvider(Provider):
    """Main application provider."""
    pass
