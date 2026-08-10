"""Internal SQLAlchemy DAO for database health checks."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    """Repository for health check operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> tuple[bool, str]:
        """Check database connectivity by executing SELECT 1.

        Returns:
            A tuple ``(healthy, detail)`` where ``detail`` is safe to expose
            externally (it contains only the exception type, never host/port).
        """
        try:
            await self._session.execute(text("SELECT 1"))
            return True, "database reachable"
        except Exception as exc:  # pragma: no cover - defensive
            return False, type(exc).__name__
