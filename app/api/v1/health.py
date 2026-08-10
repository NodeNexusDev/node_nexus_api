"""Health check endpoints."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Response, status

from app.application.services.health_service import HealthService
from app.schemas.health import ReadyCheck, ReadyResponse

router = APIRouter(route_class=DishkaRoute)


def _get_app_version() -> str:
    """Get application version from package metadata."""
    try:
        return pkg_version("node-nexus-api")
    except PackageNotFoundError:
        return "unknown"


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe — checks if the process is running.

    No authentication required (for Kubernetes liveness probes).
    """
    return {"status": "healthy", "version": _get_app_version()}


@router.get("/ready")
@inject
async def readiness_check(
    service: FromDishka[HealthService],
    response: Response,
) -> ReadyResponse:
    """Readiness probe — checks database connectivity and scheduler state.

    No authentication required (for Kubernetes readiness probes).
    """
    db_status, db_detail = await service.check_db()
    scheduler_status, scheduler_detail = service.check_scheduler()
    overall = "ready" if db_status == "ok" and scheduler_status == "ok" else "not_ready"
    if overall == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status=overall,
        checks={
            "database": ReadyCheck(status=db_status, detail=db_detail),
            "scheduler": ReadyCheck(status=scheduler_status, detail=scheduler_detail),
        },
    )
