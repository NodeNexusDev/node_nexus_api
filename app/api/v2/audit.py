"""Audit log API v2 — facade aggregating split handlers."""

from __future__ import annotations

import structlog
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter

import app.api.v2.audit_handlers.listing as _listing
import app.api.v2.audit_handlers.management as _management
import app.api.v2.audit_handlers.stats as _stats
from app.api.pagination import decode_offset, encode_offset
from app.api.v2.audit_handlers.listing import _to_response  # noqa: F401
from app.api.v2.audit_handlers.listing import router as listing_router
from app.api.v2.audit_handlers.management import router as management_router
from app.api.v2.audit_handlers.stats import router as stats_router

# Compatibility aliases for tests
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

# Shared audit logger for tests patching `app.api.v2.audit.audit`
audit = structlog.get_logger("audit")

# Ensure handlers share the same logger instance
_listing.audit = audit  # type: ignore[attr-defined]  # noqa: E501
_management.audit = audit  # type: ignore[attr-defined]  # noqa: E501
_stats.audit = audit  # type: ignore[attr-defined]  # noqa: E501

__all__ = [
    "_decode_offset",
    "_encode_offset",
    "_to_response",
    "audit",
    "router",
]

router = APIRouter(prefix="/audit", tags=["audit"], route_class=DishkaRoute)
router.include_router(stats_router)
router.include_router(management_router)
router.include_router(listing_router)
