"""Regression: DomainError raised inside audit handlers must propagate unmapped.

The generic try blocks in audit_handlers/stats.py (get_stats) and
audit_handlers/listing.py (get single, map single) must re-raise DomainError
first so domain_error_handler sees the original error with its mapped status
instead of a wrapped AuditReadError (500).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.api.v2.audit import router
from app.application.services.audit_log_service import AuditLogService
from app.core.config import Settings
from app.core.exceptions import AuditReadError, DomainError, NodeNotFoundError
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


class _SentinelReadError(AuditReadError):
    """Distinctive AuditReadError proving the original propagates unwrapped."""


def _create_audit_app(service_mock: AsyncMock | MagicMock) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(router, prefix="/api/v2")

    class AuditTestProvider(Provider):
        @provide(scope=Scope.APP)
        def get_service(self) -> AuditLogService:
            return as_typed_mock(AuditLogService, service_mock)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:
            from app.core.config import get_settings

            return get_settings()

    container = make_async_container(AuditTestProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


async def _get(app: FastAPI, url: str) -> Any:
    with patch(
        "app.core.config.get_settings",
        return_value=_mock_settings("test-master"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            return await client.get(url)


class TestStatsDomainReraise:
    async def test_stats_404_domain_error_keeps_404(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(side_effect=NodeNotFoundError("node gone"))
        app = _create_audit_app(service_mock=svc)
        resp = await _get(app, "/api/v2/audit/stats")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NodeNotFoundError"

    async def test_stats_audit_read_error_stays_unmapped(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            side_effect=_SentinelReadError("sentinel-stats-read")
        )
        app = _create_audit_app(service_mock=svc)
        resp = await _get(app, "/api/v2/audit/stats")
        assert resp.status_code == 500
        # The original error type must reach the handler, not a wrapper.
        assert resp.json()["code"] == "_SentinelReadError"


class TestGetSingleDomainReraise:
    async def test_get_single_404_domain_error_keeps_404(self) -> None:
        svc = AsyncMock()
        svc.get_log = AsyncMock(side_effect=NodeNotFoundError("log gone"))
        app = _create_audit_app(service_mock=svc)
        resp = await _get(app, f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NodeNotFoundError"

    async def test_map_single_domain_error_reraises_unmapped(self) -> None:
        svc = AsyncMock()
        svc.get_log = AsyncMock(return_value=MagicMock())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.v2.audit_handlers.listing.AuditLogResponse.model_validate",
            side_effect=NodeNotFoundError("map sentinel"),
        ):
            resp = await _get(app, f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NodeNotFoundError"
