"""Unit tests for audit API endpoint with mocked service via dishka."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.audit import router as audit_router
from app.application.dto.audit import AuditLogDTO, AuditLogPageDTO
from app.application.services.audit_log_service import AuditLogService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_log(**overrides: Any) -> AuditLogDTO:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "action": "create",
        "user": None,
        "details": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return AuditLogDTO(**defaults)


def _create_test_app(service: AuditLogService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(audit_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> AuditLogService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=AuditLogService)


@pytest.fixture
async def client(mock_service: AsyncMock) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(mock_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


class TestGetAuditLogs:
    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        response = await client.get("/api/v1/audit/")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_returns_logs(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        logs = [_make_log(action="create"), _make_log(action="update")]
        mock_service.get_logs.return_value = AuditLogPageDTO(items=tuple(logs), total=2)
        response = await client.get("/api/v1/audit/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2
        assert data["items"][0]["action"] == "create"

    async def test_filter_by_node_id(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        mock_service.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        await client.get(f"/api/v1/audit/?node_id={node_id}")
        mock_service.get_logs.assert_called_once_with(
            node_id=node_id,
            action=None,
            user=None,
            date_from=None,
            date_to=None,
            page=1,
            size=20,
        )

    async def test_filter_by_action(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        await client.get("/api/v1/audit/?action=delete")
        mock_service.get_logs.assert_called_once_with(
            node_id=None,
            action="delete",
            user=None,
            date_from=None,
            date_to=None,
            page=1,
            size=20,
        )

    async def test_pagination_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        await client.get("/api/v1/audit/?page=3&size=10")
        mock_service.get_logs.assert_called_once_with(
            node_id=None,
            action=None,
            user=None,
            date_from=None,
            date_to=None,
            page=3,
            size=10,
        )


# --- DELETE /api/v1/audit tests ---


class TestDeleteAuditLogs:
    async def test_delete_requires_master_key(self, mock_service: AsyncMock) -> None:
        """DELETE /audit requires master key."""
        app = _create_test_app(mock_service)
        with patch(
            "app.api.deps.get_settings", return_value=_mock_settings("test-master")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "nnk_not_master_key"},
            ) as client:
                resp = await client.delete("/api/v1/audit/?confirm=yes")
        assert resp.status_code == 403
        assert "master key" in resp.json()["detail"].lower()

    async def test_delete_requires_confirm(self, mock_service: AsyncMock) -> None:
        """DELETE /audit without confirm=yes returns 422."""
        app = _create_test_app(mock_service)
        with patch(
            "app.api.deps.get_settings", return_value=_mock_settings("test-master")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.delete("/api/v1/audit/")
        assert resp.status_code == 422
        assert "confirm=yes" in resp.json()["detail"]

    async def test_delete_with_master_key_and_confirm(
        self, mock_service: AsyncMock
    ) -> None:
        """DELETE /audit with master key and confirm=yes succeeds."""
        mock_service.delete_all_logs.return_value = 10

        app = _create_test_app(mock_service)
        with patch(
            "app.api.deps.get_settings", return_value=_mock_settings("test-master")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.delete("/api/v1/audit/?confirm=yes")
        assert resp.status_code == 204
        mock_service.delete_all_logs.assert_called_once()
