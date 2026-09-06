# ruff: noqa: F401, I001
"""Compose project HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.compose_handlers.query_handlers.inspect_handlers.ps_logs import (  # noqa: E501
    router as ps_logs_router,
)
from app.api.v2.compose_handlers.query_handlers.inspect_handlers.top_port import (  # noqa: E501
    router as top_port_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(ps_logs_router)
router.include_router(top_port_router)
