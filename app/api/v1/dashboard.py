"""Dashboard API endpoint."""

from dataclasses import asdict
from datetime import datetime
from typing import Literal

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import Principal, get_current_principal
from app.application.dto.dashboard import (
    DashboardDTO,
)
from app.application.services.dashboard_metrics_service import (
    DashboardMetricsService,
)
from app.application.services.dashboard_service import DashboardService
from app.schemas.dashboard import (
    DashboardDockerStats,
    DashboardMetricsResponse,
    DashboardResponse,
    EntityStats,
    MetricsBucket,
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
        docker=DashboardDockerStats(
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
    _key: Principal = Security(get_current_principal),
) -> DashboardResponse:
    """Get aggregated dashboard overview."""
    audit.info("api.dashboard.get")
    dto = await service.get_dashboard()
    return _to_response(dto)


@router.get("/metrics", response_model=DashboardMetricsResponse)
@inject
async def get_dashboard_metrics(
    metrics_service: FromDishka[DashboardMetricsService],
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    group_by: Literal["day", "hour", "week", "month"] = Query("day"),
    _key: Principal = Security(get_current_principal),
) -> DashboardMetricsResponse:
    """Get time-series execution metrics for charts."""
    audit.info(
        "api.dashboard.metrics",
        group_by=group_by,
    )
    dto = await metrics_service.get_metrics(
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
    )
    return DashboardMetricsResponse(
        command_metrics=[
            MetricsBucket.model_validate(asdict(b)) for b in dto.command_metrics
        ],
        script_metrics=[
            MetricsBucket.model_validate(asdict(b)) for b in dto.script_metrics
        ],
    )
