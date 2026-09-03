# ruff: noqa: F401, I001
"""Script executions HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.scripts_handlers.executions_handlers.exec import bulk_executions
from app.api.v2.scripts_handlers.executions_handlers.exec import router as exec_router
from app.api.v2.scripts_handlers.executions_handlers.lifecycle import (
    router as lifecycle_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(exec_router)
router.include_router(lifecycle_router)

__all__ = ["bulk_executions", "router"]
