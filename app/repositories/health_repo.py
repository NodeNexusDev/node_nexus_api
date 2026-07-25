"""Health check repository."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    """Repository for health check operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> bool:
        """Check database connectivity by executing SELECT 1.

        Returns:
            True if database is reachable, False otherwise.
        """
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
