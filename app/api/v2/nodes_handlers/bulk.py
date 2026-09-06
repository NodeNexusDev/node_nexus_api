# ruff: noqa: F401, I001
"""Node API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.nodes_handlers.bulk_handlers.observability import (  # noqa: E501
    router as observability_router,
)
from app.api.v2.nodes_handlers.bulk_handlers.operations import (  # noqa: E501
    router as operations_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(operations_router)
router.include_router(observability_router)
