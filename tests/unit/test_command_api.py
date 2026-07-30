"""Unit tests for Command API endpoints with mocked service via dishka."""

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

from app.api.error_mapping import domain_error_handler
from app.api.v1.commands import router as commands_router
from app.api.v1.health import router as health_router
from app.application.dto.command_management import CommandViewDTO
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.command_management_service import CommandManagementService
from app.core.exceptions import (
    CommandNotFoundError,
    ConnectionFailedError,
    DomainError,
    NodeNotFoundError,
    TemplateRenderError,
)
from app.schemas.command import CommandResult
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_command(**overrides: Any) -> CommandViewDTO:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "check_disk",
        "description": "Check disk usage",
        "command": "df -h",
        "parameters": (),
        "tags": (),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return CommandViewDTO(**defaults)


def _create_test_app(service: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(health_router)
    app.include_router(commands_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_management_service(self) -> CommandManagementService:
            return service

        @provide(scope=Scope.REQUEST)
        def get_execution_service(self) -> CommandExecutionService:
            return service

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


@pytest.fixture
def mock_service() -> AsyncMock:
    return AsyncMock()


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


# --- GET /commands/ ---


class TestGetCommands:
    async def test_empty_list(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_all_commands.return_value = ([], 0)
        response = await client.get("/api/v1/commands")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_returns_commands(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        cmds = [_make_command(name="c1"), _make_command(name="c2")]
        mock_service.get_all_commands.return_value = (cmds, 2)
        response = await client.get("/api/v1/commands")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 2

    async def test_pagination_params(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_all_commands.return_value = ([], 0)
        await client.get("/api/v1/commands?page=2&size=10")
        mock_service.get_all_commands.assert_called_once_with(
            page=2, size=10, tags=None
        )


# --- GET /commands/{id} ---


class TestGetCommand:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        cmd = _make_command()
        mock_service.get_command.return_value = cmd
        response = await client.get(f"/api/v1/commands/{cmd.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(cmd.id)

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.get_command.side_effect = CommandNotFoundError("not found")
        response = await client.get(f"/api/v1/commands/{uuid.uuid4()}")
        assert response.status_code == 404


# --- POST /commands/ ---


class TestCreateCommand:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        cmd = _make_command(name="new_cmd")
        mock_service.create_command.return_value = cmd
        response = await client.post(
            "/api/v1/commands",
            json={"name": "new_cmd", "command": "echo test"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "new_cmd"

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post("/api/v1/commands", json={"name": "only-name"})
        assert response.status_code == 422


# --- PUT /commands/{id} ---


class TestUpdateCommand:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        cmd = _make_command(name="updated")
        mock_service.update_command.return_value = cmd
        response = await client.put(
            f"/api/v1/commands/{cmd.id}",
            json={"name": "updated"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated"

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.update_command.side_effect = CommandNotFoundError("not found")
        response = await client.put(
            f"/api/v1/commands/{uuid.uuid4()}",
            json={"name": "x"},
        )
        assert response.status_code == 404

    async def test_preserves_explicit_null(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        cmd = _make_command(description=None)
        mock_service.update_command.return_value = cmd

        response = await client.put(
            f"/api/v1/commands/{cmd.id}",
            json={"description": None},
        )

        assert response.status_code == 200
        update = mock_service.update_command.call_args.args[1]
        assert dict(update.changes) == {"description": None}


# --- DELETE /commands/{id} ---


class TestDeleteCommand:
    async def test_found(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        mock_service.delete_command.return_value = True
        response = await client.delete(f"/api/v1/commands/{uuid.uuid4()}")
        assert response.status_code == 204

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.delete_command.side_effect = CommandNotFoundError("not found")
        response = await client.delete(f"/api/v1/commands/{uuid.uuid4()}")
        assert response.status_code == 404


# --- POST /commands/{id}/execute ---


class TestExecuteCommand:
    async def test_success(self, client: AsyncClient, mock_service: AsyncMock) -> None:
        result = CommandResult(stdout="ok", stderr="", exit_code=0)
        mock_service.execute_command.return_value = result
        response = await client.post(
            f"/api/v1/commands/{uuid.uuid4()}/execute",
            json={"node_id": str(uuid.uuid4()), "params": {}},
        )
        assert response.status_code == 200
        assert response.json()["stdout"] == "ok"
        assert response.json()["exit_code"] == 0

    async def test_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.side_effect = CommandNotFoundError("not found")
        response = await client.post(
            f"/api/v1/commands/{uuid.uuid4()}/execute",
            json={"node_id": str(uuid.uuid4()), "params": {}},
        )
        assert response.status_code == 404

    async def test_maps_params_to_immutable_request(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.return_value = CommandResult(
            stdout="ok",
            stderr="",
            exit_code=0,
        )
        command_id = uuid.uuid4()
        node_id = uuid.uuid4()

        response = await client.post(
            f"/api/v1/commands/{command_id}/execute",
            json={"node_id": str(node_id), "params": {"service": "nginx"}},
        )

        assert response.status_code == 200
        request = mock_service.execute_command.call_args.args[1]
        assert request.node_id == node_id
        assert request.params == (("service", "nginx"),)

    async def test_node_not_found(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.side_effect = NodeNotFoundError("node not found")
        response = await client.post(
            f"/api/v1/commands/{uuid.uuid4()}/execute",
            json={"node_id": str(uuid.uuid4()), "params": {}},
        )
        assert response.status_code == 404

    async def test_render_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.side_effect = TemplateRenderError("bad template")
        response = await client.post(
            f"/api/v1/commands/{uuid.uuid4()}/execute",
            json={"node_id": str(uuid.uuid4()), "params": {}},
        )
        assert response.status_code == 422

    async def test_connection_failed(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        mock_service.execute_command.side_effect = ConnectionFailedError("refused")
        response = await client.post(
            f"/api/v1/commands/{uuid.uuid4()}/execute",
            json={"node_id": str(uuid.uuid4()), "params": {}},
        )
        assert response.status_code == 503

    async def test_validation_error(
        self, client: AsyncClient, mock_service: AsyncMock
    ) -> None:
        response = await client.post(
            f"/api/v1/commands/{uuid.uuid4()}/execute",
            json={},
        )
        assert response.status_code == 422
