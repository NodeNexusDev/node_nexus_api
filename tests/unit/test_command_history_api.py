"""Unit tests for node command history API endpoint."""

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

from app.api.v1.nodes import router as nodes_router
from app.application.dto.command_history import (
    CommandHistoryDTO,
    CommandHistoryPageDTO,
)
from app.application.services.bulk_command_history_service import (
    BulkCommandHistoryService,
)
from app.application.services.command_history_service import CommandHistoryService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_history(**overrides: Any) -> CommandHistoryDTO:
    node_id = overrides.get("node_id", uuid.uuid4())
    now = datetime.now(UTC)
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "node_id": node_id,
        "command_id": None,
        "batch_id": None,
        "command_fingerprint": "a" * 64,
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "stdout_bytes": 2,
        "stderr_bytes": 0,
        "truncated": False,
        "started_at": now,
        "finished_at": now,
        "created_at": now,
    }
    defaults.update(overrides)
    return CommandHistoryDTO(**defaults)


def _create_test_app(
    service: AsyncMock, bulk_service: AsyncMock | None = None
) -> FastAPI:
    app = FastAPI()
    app.include_router(nodes_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.APP)
        def get_history_service(self) -> CommandHistoryService:
            return service

        @provide(scope=Scope.APP)
        def get_bulk_history_service(self) -> BulkCommandHistoryService:
            return bulk_service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=CommandHistoryService)


@pytest.fixture
def mock_bulk_service() -> AsyncMock:
    return AsyncMock(spec=BulkCommandHistoryService)


@pytest.fixture
async def client(
    mock_service: AsyncMock, mock_bulk_service: AsyncMock
) -> AsyncGenerator[AsyncClient]:
    app = _create_test_app(mock_service, mock_bulk_service)
    with patch("app.api.deps.get_settings", return_value=_mock_settings("test-master")):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
            headers={"X-API-Key": "test-master"},
        ) as ac:
            yield ac


class TestGetCommandHistory:
    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        mock_service.get_node_history.return_value = CommandHistoryPageDTO(
            items=(), total=0
        )
        response = await client.get(f"/api/v1/nodes/{node_id}/commands/history")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_returns_history(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        records = [
            _make_history(node_id=node_id, exit_code=0),
            _make_history(node_id=node_id, exit_code=1),
        ]
        mock_service.get_node_history.return_value = CommandHistoryPageDTO(
            items=tuple(records), total=2
        )
        response = await client.get(f"/api/v1/nodes/{node_id}/commands/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2
        assert data["items"][0]["exit_code"] == 0
        assert data["items"][0]["command_fingerprint"] == "a" * 64

    async def test_pagination_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        node_id = uuid.uuid4()
        mock_service.get_node_history.return_value = CommandHistoryPageDTO(
            items=(), total=0
        )
        await client.get(f"/api/v1/nodes/{node_id}/commands/history?page=2&size=10")
        mock_service.get_node_history.assert_called_once_with(node_id, page=2, size=10)


class TestGetBulkCommandHistory:
    async def test_empty_bulk_history(
        self, client: AsyncClient, mock_bulk_service: AsyncMock
    ) -> None:
        batch_id = uuid.uuid4()
        mock_bulk_service.get_batch_history.return_value = CommandHistoryPageDTO(
            items=(), total=0
        )
        response = await client.get(
            "/api/v1/nodes/bulk/history",
            params={"batch_id": str(batch_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_returns_bulk_history(
        self, client: AsyncClient, mock_bulk_service: AsyncMock
    ) -> None:
        batch_id = uuid.uuid4()
        records = [
            _make_history(batch_id=batch_id, exit_code=0),
            _make_history(batch_id=batch_id, exit_code=1),
        ]
        mock_bulk_service.get_batch_history.return_value = CommandHistoryPageDTO(
            items=tuple(records), total=2
        )
        response = await client.get(
            "/api/v1/nodes/bulk/history",
            params={"batch_id": str(batch_id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2
        assert data["items"][0]["exit_code"] == 0

    async def test_pagination_params(
        self, client: AsyncClient, mock_bulk_service: AsyncMock
    ) -> None:
        batch_id = uuid.uuid4()
        mock_bulk_service.get_batch_history.return_value = CommandHistoryPageDTO(
            items=(), total=0
        )
        await client.get(
            "/api/v1/nodes/bulk/history",
            params={"batch_id": str(batch_id), "page": "2", "size": "10"},
        )
        mock_bulk_service.get_batch_history.assert_called_once_with(
            batch_id, page=2, size=10
        )
