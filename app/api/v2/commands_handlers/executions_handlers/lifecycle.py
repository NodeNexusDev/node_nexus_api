# ruff: noqa: F401, I001
"""Command API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.commands_handlers.executions_handlers.lifecycle_handlers.history import (  # noqa: E501
    router as history_router,
)
from app.api.v2.commands_handlers.executions_handlers.lifecycle_handlers.ops import (  # noqa: E501
    router as ops_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(history_router)
router.include_router(ops_router)
