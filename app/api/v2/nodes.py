"""Node API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.pagination import decode_offset, encode_offset
from app.api.v2.nodes_handlers.bulk import router as bulk_router
from app.api.v2.nodes_handlers.crud import _node_response  # noqa: F401
from app.api.v2.nodes_handlers.crud import router as crud_router
from app.api.v2.nodes_handlers.history import router as history_router
from app.api.v2.nodes_handlers.listing import router as listing_router
from app.schemas.common import decode_cursor, encode_cursor

# Compatibility aliases for tests
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

__all__ = [
    "_decode_offset",
    "_encode_offset",
    "_node_response",
    "decode_cursor",
    "encode_cursor",
    "router",
]

router = APIRouter(prefix="/nodes", tags=["nodes"], route_class=DishkaRoute)
router.include_router(listing_router)
router.include_router(bulk_router)
router.include_router(history_router)
router.include_router(crud_router)
