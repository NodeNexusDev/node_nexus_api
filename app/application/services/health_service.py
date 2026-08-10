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

    async def check_db(self) -> tuple[str, str]:
        """Check database connectivity and return a public-safe status/detail."""
        ok, detail = await self._repository.ping()
        return ("ok" if ok else "error"), detail

    def check_scheduler(self) -> tuple[str, str]:
        """Check scheduler state and return a public-safe status/detail."""
        if not self._scheduler_enabled:
            return "ok", "scheduler disabled"
        if self._scheduler is None:
            return "error", "scheduler unavailable"
        ready = self._scheduler.is_ready()
        owns = self._scheduler.owns_execution()
        jobs = len(self._scheduler.inspect())
        detail = f"ready={ready}, owns={owns}, jobs={jobs}"
        return ("ok" if ready else "error"), detail
