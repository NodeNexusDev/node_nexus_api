# ruff: noqa: F401, I001
"""Docker images HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.docker_handlers.images_handlers.listing import router as listing_router
from app.api.v2.docker_handlers.images_handlers.ops import router as ops_router

router = APIRouter(tags=["docker"], route_class=DishkaRoute)
router.include_router(listing_router)
router.include_router(ops_router)
