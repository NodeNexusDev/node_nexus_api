"""Docker containers HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.pagination import decode_offset, encode_offset, paginate_offset
from app.api.v2.docker_handlers.containers_handlers.bulk import router as bulk_router
from app.api.v2.docker_handlers.containers_handlers.crud import router as crud_router
from app.api.v2.docker_handlers.containers_handlers.exec_inspect import (
    router as exec_inspect_router,
)
from app.api.v2.docker_handlers.containers_handlers.lifecycle import (
    router as lifecycle_router,
)

# Compatibility aliases for tests
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816
_paginate_offset = paginate_offset  # noqa: N816

__all__ = [
    "_decode_offset",
    "_encode_offset",
    "_paginate_offset",
    "router",
]

router = APIRouter(tags=["docker"], route_class=DishkaRoute)
router.include_router(crud_router)
router.include_router(lifecycle_router)
router.include_router(exec_inspect_router)
router.include_router(bulk_router)
