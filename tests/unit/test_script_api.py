"""Unit tests for Script API endpoints with mocked service via dishka."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.health import router as health_router
from app.api.v1.scripts import router as scripts_router
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    NodeNotFoundError,
    ScriptNotFoundError,
    TemplateRenderError,
)
from app.schemas.script import (
    ScriptExecutionBatchResult,
    ScriptResponse,
    ScriptStepResult,
)
from app.services.script_service import ScriptService
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_step_result(**overrides: Any) -> ScriptStepResult:
    defaults: dict[str, Any] = {
        "step_index": 0,
        "label": "Check",
        "command": "df -h",
        "stdout": "",
        "stderr": "",
        "exit_code": 0,
    }
    defaults.update(overrides)
    return ScriptStepResult(**defaults)


def _make_script(**overrides: Any) -> ScriptResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "deploy_check",
        "description": "Pre-deploy check",
        "steps": [
            {
                "label": "Check disk",
                "type": "inline",
                "command": "df -h",
                "on_failure": "stop",
            }
        ],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ScriptResponse(**defaults)


def _make_batch_result(**overrides: Any) -> ScriptExecutionBatchResult:
    defaults: dict[str, Any] = {
        "script_id": uuid.uuid4(),
        "results": [],
    }
    defaults.update(overrides)
    return ScriptExecutionBatchResult(**defaults)


def _create_test_app(service: ScriptService | AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(scripts_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_service(self) -> ScriptService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock(spec=ScriptService)


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


# --- GET /scripts/ ---


class TestGetScripts:
    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_all_scripts.return_value = ([], 0)
        response = await client.get("/api/v1/scripts")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_returns_scripts(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        scripts = [_make_script(name="s1"), _make_script(name="s2")]
        mock_service.get_all_scripts.return_value = (scripts, 2)
        response = await client.get("/api/v1/scripts")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    async def test_pagination_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_all_scripts.return_value = ([], 0)
        await client.get("/api/v1/scripts?page=2&size=10")
        mock_service.get_all_scripts.assert_called_once_with(page=2, size=10)


# --- GET /scripts/{id} ---


class TestGetScript:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        script = _make_script()
        mock_service.get_script.return_value = script
        response = await client.get(f"/api/v1/scripts/{script.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(script.id)

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_script.side_effect = ScriptNotFoundError("not found")
        response = await client.get(f"/api/v1/scripts/{uuid.uuid4()}")
        assert response.status_code == 404


# --- POST /scripts/ ---


class TestCreateScript:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        script = _make_script(name="new_script")
        mock_service.create_script.return_value = script
        response = await client.post(
            "/api/v1/scripts",
            json={
                "name": "new_script",
                "steps": [{"label": "Step 1", "type": "inline", "command": "echo ok"}],
            },
        )
        assert response.status_code == 201
        assert response.json()["name"] == "new_script"

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post("/api/v1/scripts", json={"name": "no-steps"})
        assert response.status_code == 422


# --- PUT /scripts/{id} ---


class TestUpdateScript:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        script = _make_script(name="updated")
        mock_service.update_script.return_value = script
        response = await client.put(
            f"/api/v1/scripts/{script.id}",
            json={"name": "updated"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated"

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.update_script.side_effect = ScriptNotFoundError("not found")
        response = await client.put(
            f"/api/v1/scripts/{uuid.uuid4()}",
            json={"name": "x"},
        )
        assert response.status_code == 404


# --- DELETE /scripts/{id} ---


class TestDeleteScript:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.delete_script.return_value = True
        response = await client.delete(f"/api/v1/scripts/{uuid.uuid4()}")
        assert response.status_code == 204

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.delete_script.side_effect = ScriptNotFoundError("not found")
        response = await client.delete(f"/api/v1/scripts/{uuid.uuid4()}")
        assert response.status_code == 404


# --- POST /scripts/{id}/execute ---


class TestExecuteScript:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        batch = _make_batch_result()
        mock_service.execute_script.return_value = batch
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        assert response.status_code == 200
        assert response.json()["results"] == []

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_script.side_effect = ScriptNotFoundError("not found")
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        assert response.status_code == 404

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_script.side_effect = NodeNotFoundError("node not found")
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        assert response.status_code == 404

    async def test_command_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_script.side_effect = CommandNotFoundError("cmd not found")
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        assert response.status_code == 404

    async def test_render_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_script.side_effect = TemplateRenderError("bad template")
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        assert response.status_code == 422

    async def test_connection_failed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_script.side_effect = ConnectionFailedError("refused")
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={"node_ids": [str(uuid.uuid4())], "params": {}},
        )
        assert response.status_code == 503

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post(
            f"/api/v1/scripts/{uuid.uuid4()}/execute",
            json={},
        )
        assert response.status_code == 422


# --- GET /scripts/{id}/executions ---


class TestGetExecutions:
    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_executions.return_value = ([], 0)
        response = await client.get(f"/api/v1/scripts/{uuid.uuid4()}/executions")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_executions.side_effect = ScriptNotFoundError("not found")
        response = await client.get(f"/api/v1/scripts/{uuid.uuid4()}/executions")
        assert response.status_code == 404

    async def test_pagination_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_executions.return_value = ([], 0)
        script_id = uuid.uuid4()
        await client.get(f"/api/v1/scripts/{script_id}/executions?page=2&size=10")
        mock_service.get_executions.assert_called_once_with(script_id, page=2, size=10)
