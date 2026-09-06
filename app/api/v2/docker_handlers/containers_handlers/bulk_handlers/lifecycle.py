# ruff: noqa: F401, I001
"""Docker containers bulk lifecycle — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.docker_handlers.containers_handlers.bulk_handlers.lifecycle_handlers.advanced import (  # noqa: E501
    router as advanced_router,
)
from app.api.v2.docker_handlers.containers_handlers.bulk_handlers.lifecycle_handlers.basic import (  # noqa: E501
    router as basic_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(basic_router)
router.include_router(advanced_router)
