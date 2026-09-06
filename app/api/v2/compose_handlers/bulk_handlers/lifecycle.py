# ruff: noqa: F401, I001
"""Compose project HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.compose_handlers.bulk_handlers.lifecycle_handlers.pause_control import (  # noqa: E501
    router as pause_router,
)
from app.api.v2.compose_handlers.bulk_handlers.lifecycle_handlers.start_stop import (  # noqa: E501
    router as start_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(start_router)
router.include_router(pause_router)
