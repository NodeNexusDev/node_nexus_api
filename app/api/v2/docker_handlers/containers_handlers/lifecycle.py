# ruff: noqa: F401, I001
"""Docker management HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.docker_handlers.containers_handlers.lifecycle_handlers.basic import (  # noqa: E501
    router as basic_router,
)
from app.api.v2.docker_handlers.containers_handlers.lifecycle_handlers.control import (  # noqa: E501
    router as control_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(basic_router)
router.include_router(control_router)
