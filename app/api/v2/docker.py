"""Docker management HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.pagination import decode_offset, encode_offset, paginate_offset
from app.api.v2.docker_handlers.containers import router as containers_router
from app.api.v2.docker_handlers.images import router as images_router
from app.api.v2.docker_handlers.networks import router as networks_router
from app.api.v2.docker_handlers.system import router as system_router
from app.api.v2.docker_handlers.volumes import router as volumes_router

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816
_paginate_offset = paginate_offset  # noqa: N816

router = APIRouter(
    prefix="/nodes/{node_id}/docker", tags=["docker"], route_class=DishkaRoute
)
router.include_router(containers_router)
router.include_router(images_router)
router.include_router(networks_router)
router.include_router(volumes_router)
router.include_router(system_router)
