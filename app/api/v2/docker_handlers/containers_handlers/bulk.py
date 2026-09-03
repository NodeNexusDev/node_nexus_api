"""Docker containers bulk HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.docker_handlers.containers_handlers.bulk_handlers.inspect import (
    router as inspect_router,
)
from app.api.v2.docker_handlers.containers_handlers.bulk_handlers.lifecycle import (
    router as lifecycle_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(lifecycle_router)
router.include_router(inspect_router)
