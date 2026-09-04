"""Compose bulk HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.compose_handlers.bulk_handlers.lifecycle import (
    router as lifecycle_router,
)
from app.api.v2.compose_handlers.bulk_handlers.ops import router as ops_router

router = APIRouter(tags=["docker-compose"], route_class=DishkaRoute)
router.include_router(lifecycle_router)
router.include_router(ops_router)
