# ruff: noqa: F401, I001
"""Docker management HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.docker_handlers.networks_handlers.listing import (  # noqa: E501
    router as listing_router,
)
from app.api.v2.docker_handlers.networks_handlers.management import (  # noqa: E501
    router as management_router,
)

router = APIRouter(tags=["docker"], route_class=DishkaRoute)
router.include_router(listing_router)
router.include_router(management_router)
