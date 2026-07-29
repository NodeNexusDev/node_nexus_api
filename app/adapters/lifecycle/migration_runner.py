"""Alembic-backed database migration lifecycle adapter."""

import asyncio

import structlog
from alembic.config import Config as AlembicConfig

from alembic import command as alembic_command

logger = structlog.get_logger()


class MigrationRunner:
    """Run pending Alembic migrations outside the event-loop thread."""

    def __init__(
        self,
        database_url: str,
        *,
        config_path: str = "alembic.ini",
    ) -> None:
        self._database_url = database_url
        self._config_path = config_path

    async def run(self) -> None:
        """Upgrade the database schema to the latest revision."""
        await asyncio.to_thread(self.run_sync)

    def run_sync(self) -> None:
        """Execute Alembic's synchronous migration command."""
        config = AlembicConfig(self._config_path)
        config.set_main_option("sqlalchemy.url", self._database_url)
        try:
            alembic_command.upgrade(config, "head")
        except Exception as exc:
            logger.exception("migrations.failed", error_type=type(exc).__name__)
            raise RuntimeError(
                "Database migrations failed. Ensure the database is reachable "
                "and the schema is compatible."
            ) from exc
