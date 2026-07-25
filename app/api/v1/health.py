"""Health check endpoints."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Response

from app.services.health_service import HealthService

router = APIRouter(route_class=DishkaRoute)


def _get_app_version() -> str:
    """Get application version from package metadata."""
    try:
        return pkg_version("node-nexus-api")
    except PackageNotFoundError:
        return "0.4.0"


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
) -> Response:
    """Readiness probe — checks database connectivity.

    No authentication required (for Kubernetes readiness probes).
    """
    db_ok = await service.check_db()
    if db_ok:
        return Response(
            content='{"status": "ready", "checks": {"database": "ok"}}',
            status_code=200,
            media_type="application/json",
        )
    return Response(
        content='{"status": "not_ready", "checks": {"database": "error"}}',
        status_code=503,
        media_type="application/json",
    )
