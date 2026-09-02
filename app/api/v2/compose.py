"""Compose project HTTP adapter v2 — facade aggregating split handlers."""

from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

from app.api.pagination import decode_offset as _decode_offset
from app.api.pagination import encode_offset as _encode_offset
from app.api.pagination import paginate_offset as _paginate_offset
from app.api.v2.compose_handlers.bulk import router as bulk_router
from app.api.v2.compose_handlers.projects import (
    _bulk_to_response,
    _to_response,
    _validate_project_name,
)
from app.api.v2.compose_handlers.projects import router as projects_router
from app.api.v2.compose_handlers.query import router as query_router
from app.api.v2.compose_handlers.updown import router as updown_router

# Re-export for tests importing private helpers
__all__ = [
    "_bulk_to_response",
    "_decode_offset",
    "_encode_offset",
    "_paginate_offset",
    "_to_response",
    "_validate_project_name",
    "router",
]

router = APIRouter(
    prefix="/nodes/{node_id}/docker/compose",
    tags=["docker-compose"],
    route_class=DishkaRoute,
)
router.include_router(projects_router)
router.include_router(updown_router)
router.include_router(bulk_router)
router.include_router(query_router)
