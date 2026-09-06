# ruff: noqa: F401, I001
"""Script executions lifecycle — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.scripts_handlers.executions_handlers.lifecycle_handlers.history import (
    router as history_router,
)
from app.api.v2.scripts_handlers.executions_handlers.lifecycle_handlers.retries import (
    router as retries_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(retries_router)
router.include_router(history_router)
