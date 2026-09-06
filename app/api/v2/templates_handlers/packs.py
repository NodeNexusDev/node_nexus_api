# ruff: noqa: F401, I001
"""Template packs HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.templates_handlers.packs_handlers.archive import (
    router as archive_router,
)
from app.api.v2.templates_handlers.packs_handlers.crud import (
    _pack_detail_response,
    _pack_response,
    _registry_response,
)
from app.api.v2.templates_handlers.packs_handlers.crud import router as crud_router

__all__ = [
    "_pack_detail_response",
    "_pack_response",
    "_registry_response",
    "router",
]

router = APIRouter(route_class=DishkaRoute)
router.include_router(crud_router)
router.include_router(archive_router)
