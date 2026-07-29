"""Health check service."""

from app.application.ports.health import DatabaseHealthProbe
from app.application.ports.schedule import JobSchedulerPort


class HealthService:
    """Service for health check operations."""

    def __init__(
        self,
        repository: DatabaseHealthProbe,
        scheduler: JobSchedulerPort | None = None,
        *,
        scheduler_enabled: bool = False,
    ) -> None:
        self._repository = repository
        self._scheduler = scheduler
        self._scheduler_enabled = scheduler_enabled

    async def check_db(self) -> bool:
        """Check database connectivity.

        Returns:
            True if database is reachable, False otherwise.
        """
        return await self._repository.ping()

    def check_scheduler(self) -> bool:
        """Check that initial persistent schedule restoration succeeded."""
        return (
            not self._scheduler_enabled
            or self._scheduler is not None
            and self._scheduler.is_ready()
        )
