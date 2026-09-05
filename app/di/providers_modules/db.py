# ruff: noqa: I001
"""DI providers for the application."""

from __future__ import annotations

from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.adapters.lifecycle.migration_runner import MigrationRunner
from app.core.config import Settings


class DbProvider(Provider):
    """Database session provider."""

    @provide(scope=Scope.APP)
    async def get_engine(self, settings: Settings) -> AsyncIterable[AsyncEngine]:
        """Get the application engine and dispose its pool on shutdown."""
        if settings.DATABASE_URL.startswith("sqlite"):
            engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        else:
            engine = create_async_engine(
                settings.DATABASE_URL,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,
                connect_args={
                    "server_settings": {"statement_timeout": "30000"},
                    "command_timeout": 30,
                },
            )
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
