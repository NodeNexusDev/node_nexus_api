# ruff: noqa: F401, I001
"""Compose query HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.compose_handlers.query_handlers.exec import router as exec_router
from app.api.v2.compose_handlers.query_handlers.inspect import router as inspect_router

router = APIRouter(tags=["docker-compose"], route_class=DishkaRoute)
router.include_router(inspect_router)
router.include_router(exec_router)
