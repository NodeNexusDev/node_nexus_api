"""Dashboard API endpoint."""

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import get_current_api_key
from app.application.dto.dashboard import (
    DashboardDTO,
)
from app.application.services.dashboard_service import DashboardService
from app.schemas.dashboard import (
    DashboardResponse,
    DockerStats,
    EntityStats,
    NodeStats,
    RecentActivity,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/dashboard", tags=["dashboard"], route_class=DishkaRoute)


def _to_response(dto: DashboardDTO) -> DashboardResponse:
    return DashboardResponse(
        nodes=NodeStats(
            total=dto.nodes.total,
            active=dto.nodes.active,
            unreachable=dto.nodes.unreachable,
        ),
        docker=DockerStats(
            total=dto.docker.total,
            running=dto.docker.running,
            stopped=dto.docker.stopped,
        ),
        scripts=EntityStats(total=dto.scripts.total),
        commands=EntityStats(total=dto.commands.total),
        recent_activity=[
            RecentActivity(
                id=entry.id,
                action=entry.action,
                node_id=entry.node_id,
                user=entry.user,
                details=entry.details,
                created_at=entry.created_at,
            )
            for entry in dto.recent_activity
        ],
    )


@router.get("/", response_model=DashboardResponse)
@inject
async def get_dashboard(
    service: FromDishka[DashboardService],
    _key: str = Security(get_current_api_key),
) -> DashboardResponse:
    """Get aggregated dashboard overview."""
    audit.info("api.dashboard.get")
    dto = await service.get_dashboard()
    return _to_response(dto)
