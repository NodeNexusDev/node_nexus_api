"""Health check service."""

from app.repositories.health_repo import HealthRepository


class HealthService:
    """Service for health check operations."""

    def __init__(self, repository: HealthRepository) -> None:
        self._repository = repository

    async def check_db(self) -> bool:
        """Check database connectivity.

        Returns:
            True if database is reachable, False otherwise.
        """
        return await self._repository.ping()
