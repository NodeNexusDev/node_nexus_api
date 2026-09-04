# ruff: noqa: F401, I001
"""Template API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.templates_handlers.installs_handlers.lifecycle import (  # noqa: E501
    router as lifecycle_router,
)
from app.api.v2.templates_handlers.installs_handlers.operations import (  # noqa: E501
    router as operations_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(lifecycle_router)
router.include_router(operations_router)
