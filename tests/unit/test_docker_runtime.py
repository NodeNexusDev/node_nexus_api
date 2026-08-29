"""Tests for the SSH-backed Docker runtime adapter."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.runtime.docker import SshDockerRuntime
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.core.exceptions import ConnectionFailedError


def _target() -> NodeConnectionDTO:
    return NodeConnectionDTO(
        id=uuid.uuid4(),
        name="docker",
        endpoint=NodeEndpoint(
            host="127.0.0.1",
            port=22,
            connection_type="ssh",
            has_docker=True,
            docker_host="unix:///var/run/docker.sock",
        ),
        credentials=NodeCredentials(username="root"),
    )


async def test_runtime_builds_and_executes_docker_command() -> None:
    connector = AsyncMock()
    connector.execute_command.return_value = ("output", "", 0)
    factory = Mock()
    factory.create_ssh.return_value = connector
    cipher = Mock()
    cipher.decrypt.side_effect = lambda value: value

    command = "DOCKER_HOST=unix:///var/run/docker.sock docker ps"
    result = await SshDockerRuntime(factory, cipher).execute(_target(), command)

    assert result.stdout == "output"
    connector.execute_command.assert_awaited_once_with(command)


async def test_runtime_maps_connector_failure() -> None:
    connector = AsyncMock()
    connector.__aenter__.side_effect = RuntimeError("offline")
    factory = Mock()
    factory.create_ssh.return_value = connector
    cipher = Mock()
    cipher.decrypt.side_effect = lambda value: value

    with pytest.raises(ConnectionFailedError, match="Docker host"):
        await SshDockerRuntime(factory, cipher).execute(_target(), "ps")
