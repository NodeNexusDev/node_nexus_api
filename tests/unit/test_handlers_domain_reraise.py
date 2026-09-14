"""Regression: DomainError raised inside swept v2 handlers must propagate unmapped.

Every ``except Exception`` block in non-audit ``app/api/v2`` handler files
that converts errors into ``HTTPException`` must re-raise ``DomainError``
first so ``domain_error_handler`` sees the original error with its mapped
status instead of a flattened 422.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.application.services.template_pack_service import TemplatePackService
from app.core.config import Settings
from app.core.exceptions import DomainError, NodeNotFoundError
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_nodes_history_app(service_mock: AsyncMock) -> FastAPI:
    from app.api.v2.nodes_handlers.history import router as hist_router

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(hist_router, prefix="/api/v2/nodes")

    class Prov(Provider):
        @provide(scope=Scope.REQUEST)
        def get_history(self) -> NodeStatusHistoryService:
            return as_typed_mock(NodeStatusHistoryService, service_mock)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:
            from app.core.config import get_settings

            return get_settings()

    container = make_async_container(Prov(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


def _make_templates_app(service_mock: AsyncMock) -> FastAPI:
    from app.api.v2.templates_handlers.packs_handlers.crud_handlers.create import (
        router as create_router,
    )

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(create_router, prefix="/api/v2/templates")

    class Prov(Provider):
        @provide(scope=Scope.REQUEST)
        def get_packs(self) -> TemplatePackService:
            return as_typed_mock(TemplatePackService, service_mock)

        @provide(scope=Scope.APP)
        def get_settings(self) -> Settings:
            from app.core.config import get_settings

            return get_settings()

    container = make_async_container(Prov(), MockAuthServiceProvider())
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


async def _post(app: FastAPI, url: str, payload: dict[str, Any]) -> Any:
    with patch(
        "app.core.config.get_settings",
        return_value=_mock_settings("test-master"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            return await client.post(url, json=payload)


def _pack_payload() -> dict[str, Any]:
    return {
        "manifest": {
            "pack_id": "sentinel-pack",
            "name": "Sentinel Pack",
            "version": "1.0.0",
        },
        "commands": [],
        "scripts": [],
    }


class TestCreatePackDomainReraise:
    async def test_typed_domain_error_keeps_mapped_status(self) -> None:
        svc = AsyncMock()
        svc.create_pack = AsyncMock(side_effect=NodeNotFoundError("pack node gone"))
        app = _make_templates_app(service_mock=svc)
        resp = await _post(app, "/api/v2/templates/packs", _pack_payload())
        # Flattened without the re-raise this would be 422 "Invalid" style.
        assert resp.status_code == 404
        assert resp.json()["code"] == "NodeNotFoundError"

    async def test_generic_domain_error_stays_unmapped(self) -> None:
        svc = AsyncMock()
        svc.create_pack = AsyncMock(side_effect=DomainError("sentinel-boom"))
        app = _make_templates_app(service_mock=svc)
        resp = await _post(app, "/api/v2/templates/packs", _pack_payload())
        assert resp.status_code == 422
        # The original error type must reach the handler, not a wrapper.
        assert resp.json()["code"] == "DomainError"

    async def test_plain_error_still_flattened_to_422(self) -> None:
        svc = AsyncMock()
        svc.create_pack = AsyncMock(side_effect=RuntimeError("kablam"))
        app = _make_templates_app(service_mock=svc)
        resp = await _post(app, "/api/v2/templates/packs", _pack_payload())
        assert resp.status_code == 422
        assert resp.json()["detail"] == "kablam"


class TestNodeHistoryDomainReraise:
    async def test_outer_decode_domain_error_reraises_unmapped(self) -> None:
        svc = AsyncMock()
        app = _make_nodes_history_app(service_mock=svc)
        node_id = uuid.uuid4()
        with patch(
            "app.api.v2.nodes_handlers.history.decode_offset",
            side_effect=NodeNotFoundError("decode sentinel"),
        ):
            resp = await _get(app, f"/api/v2/nodes/{node_id}/status-history?cursor=abc")
        # Flattened without the re-raise this would be 422 Invalid cursor.
        assert resp.status_code == 404
        assert resp.json()["code"] == "NodeNotFoundError"

    async def test_inner_decode_domain_error_reraises_unmapped(self) -> None:
        svc = AsyncMock()
        app = _make_nodes_history_app(service_mock=svc)
        node_id = uuid.uuid4()
        with (
            patch(
                "app.api.v2.nodes_handlers.history.decode_offset",
                side_effect=ValueError("bad"),
            ),
            patch(
                "app.api.v2.nodes_handlers.history.decode_cursor",
                side_effect=NodeNotFoundError("map sentinel"),
            ),
        ):
            resp = await _get(app, f"/api/v2/nodes/{node_id}/status-history?cursor=abc")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NodeNotFoundError"
