"""Unit tests for command history persistence in NodeCommandService."""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.command_execution import CommandRequestDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_command_service import NodeCommandService


@pytest.fixture
def history_writer() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def node_reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def connector_factory() -> Mock:
    return Mock()


@pytest.fixture
def service(
    node_reader: AsyncMock,
    connector_factory: Mock,
    history_writer: AsyncMock,
) -> NodeCommandService:
    return NodeCommandService(
        node_reader=node_reader,
        status_writer=AsyncMock(),
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=connector_factory,
        history_writer=history_writer,
    )


async def test_execute_command_saves_history(
    service: NodeCommandService,
    node_reader: AsyncMock,
    connector_factory: Mock,
    history_writer: AsyncMock,
) -> None:
    node_id = uuid.uuid4()
    node_reader.get_connection.return_value = NodeConnectionDTO(
        id=node_id,
        name="node",
        endpoint=NodeEndpoint(host="127.0.0.1", port=22, connection_type="ssh"),
        credentials=NodeCredentials(username="root"),
    )
    connector = AsyncMock()
    connector.execute_command.return_value = ("hello", "", 0)
    connector_factory.create_ssh.return_value = connector

    result = await service.execute_command(
        node_id, CommandRequestDTO(command="echo hello")
    )

    assert result.exit_code == 0
    history_writer.save.assert_awaited_once()
    saved = history_writer.save.await_args.args[0]
    assert saved.node_id == node_id
    assert saved.exit_code == 0
    assert saved.stdout == "hello"
    assert saved.stderr == ""
    assert saved.command_fingerprint is not None
    assert len(saved.command_fingerprint) == 64


async def test_execute_command_without_history_writer_does_not_fail(
    node_reader: AsyncMock,
    connector_factory: Mock,
) -> None:
    node_id = uuid.uuid4()
    node_reader.get_connection.return_value = NodeConnectionDTO(
        id=node_id,
        name="node",
        endpoint=NodeEndpoint(host="127.0.0.1", port=22, connection_type="ssh"),
        credentials=NodeCredentials(username="root"),
    )
    connector = AsyncMock()
    connector.execute_command.return_value = ("ok", "", 0)
    connector_factory.create_ssh.return_value = connector

    service = NodeCommandService(
        node_reader=node_reader,
        status_writer=AsyncMock(),
        credential_cipher=AesGcmCredentialCipher(),
        connector_factory=connector_factory,
    )

    result = await service.execute_command(
        node_id, CommandRequestDTO(command="echo ok")
    )

    assert result.exit_code == 0
