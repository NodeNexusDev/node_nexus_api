# ruff: noqa: F401, I001
"""Compose project HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.compose_handlers.bulk_handlers.ops_handlers.manage import (  # noqa: E501
    router as manage_router,
)
from app.api.v2.compose_handlers.bulk_handlers.ops_handlers.sync import (  # noqa: E501
    router as sync_router,
)

router = APIRouter(route_class=DishkaRoute)
router.include_router(manage_router)
router.include_router(sync_router)
