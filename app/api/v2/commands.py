"""Command API v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.pagination import decode_offset, encode_offset
from app.api.v2.commands_handlers.crud import (
    _command_response,  # noqa: F401
    _parameter_dto,  # noqa: F401
)
from app.api.v2.commands_handlers.crud import router as crud_router
from app.api.v2.commands_handlers.executions import bulk_executions  # noqa: F401
from app.api.v2.commands_handlers.executions import router as executions_router
from app.api.v2.commands_handlers.history import router as history_router
from app.api.v2.commands_handlers.listing import router as listing_router
from app.api.v2.commands_handlers.stats import router as stats_router

# Compatibility aliases for tests
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

__all__ = [
    "_command_response",
    "_decode_offset",
    "_encode_offset",
    "_parameter_dto",
    "bulk_executions",
    "router",
]

router = APIRouter(prefix="/commands", tags=["commands"], route_class=DishkaRoute)
router.include_router(listing_router)
router.include_router(history_router)
router.include_router(stats_router)
router.include_router(executions_router)
router.include_router(crud_router)
