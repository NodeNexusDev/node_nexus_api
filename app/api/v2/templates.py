"""Template API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.pagination import decode_offset, encode_offset
from app.api.v2.templates_handlers.installs import router as installs_router
from app.api.v2.templates_handlers.packs import (
    _pack_detail_response,  # noqa: F401
    _pack_response,  # noqa: F401
    _registry_response,  # noqa: F401
)
from app.api.v2.templates_handlers.packs import router as packs_router
from app.api.v2.templates_handlers.registries import router as registries_router

# Compatibility aliases for tests
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

__all__ = [
    "_decode_offset",
    "_encode_offset",
    "_pack_detail_response",
    "_pack_response",
    "_registry_response",
    "router",
]

router = APIRouter(prefix="/templates", tags=["templates"], route_class=DishkaRoute)
router.include_router(registries_router)
router.include_router(packs_router)
router.include_router(installs_router)
