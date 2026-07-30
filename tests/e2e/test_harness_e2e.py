"""Executable checks for the reusable E2E harness."""

import asyncpg
import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController
from tests.e2e.helpers.websocket import WebSocketClientFactory

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]


@pytest.mark.asyncio
async def test_full_stack_harness(
    api_base_url: str,
    websocket_base_url: str,
    async_e2e_client: httpx.AsyncClient,
    postgres_connection: asyncpg.Connection,
    websocket_client: WebSocketClientFactory,
    docker_service_controller: DockerServiceController,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """All harness boundaries are usable against the running stack."""
    response = await async_e2e_client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"

    assert api_base_url.startswith("http://")
    assert websocket_base_url.startswith("ws://")
    assert websocket_client.base_url == websocket_base_url
    assert await postgres_connection.fetchval("SELECT 1") == 1

    command = e2e_resources.create_command()
    assert command["name"].startswith("e2e-command-")

    api_logs = docker_service_controller.logs("api", tail=20)
    assert isinstance(api_logs, str)
