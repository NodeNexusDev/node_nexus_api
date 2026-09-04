# ruff: noqa: F401, I001
"""Template API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.v2.templates_handlers.packs_handlers.crud_handlers.create import (  # noqa: E501
    _pack_detail_response,
    _pack_response,
    _registry_response,
    router as create_router,
)
from app.api.v2.templates_handlers.packs_handlers.crud_handlers.listing import (  # noqa: E501
    router as listing_router,
)

__all__ = [
    "_pack_detail_response",
    "_pack_response",
    "_registry_response",
    "router",
]

router = APIRouter(route_class=DishkaRoute)
router.include_router(create_router)
router.include_router(listing_router)
