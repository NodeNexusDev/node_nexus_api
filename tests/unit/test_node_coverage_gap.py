"""Targeted tests for uncovered lines in node_command_service.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.command_execution import CommandRequestDTO
from app.application.services.node_command_service import NodeCommandService
from app.core.exceptions import NodeNotFoundError
from tests.unit.conftest import make_node_view, make_orm_node, make_response


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_factory() -> MagicMock:
    factory = MagicMock()
    mock_connector = AsyncMock()
    mock_connector.execute_command.return_value = ("ok", "", 0)
    mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
    mock_connector.__aexit__ = AsyncMock(return_value=False)
    factory.create_ssh.return_value = mock_connector
    return factory


class TestCheckConnectivityExtra:
    async def test_status_history_writer_called(self) -> None:
        repo = AsyncMock()
        factory = MagicMock()
        mock_connector = AsyncMock()
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=False)
        factory.create_ssh.return_value = mock_connector

        history_writer = AsyncMock()
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_connection.return_value = orm_node
        repo.update_node_status.return_value = make_node_view(
            id=node_response.id,
        )

        svc = NodeCommandService(
            node_reader=repo,
            status_writer=repo,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=factory,
            status_history_writer=history_writer,
        )
        await svc.check_connectivity(node_response.id)
        history_writer.save.assert_awaited_once()

    async def test_update_returns_none_raises(self) -> None:
        repo = AsyncMock()
        factory = MagicMock()
        mock_connector = AsyncMock()
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=False)
        factory.create_ssh.return_value = mock_connector

        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_connection.return_value = orm_node
        repo.update_node_status.return_value = None

        svc = NodeCommandService(
            node_reader=repo,
            status_writer=repo,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=factory,
        )
        with pytest.raises(NodeNotFoundError):
            await svc.check_connectivity(node_response.id)


class TestExecuteCommandExtra:
    async def test_timeout_passed_to_connector(self) -> None:
        repo = AsyncMock()
        factory = MagicMock()
        mock_connector = AsyncMock()
        mock_connector.execute_command.return_value = ("ok", "", 0)
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=False)
        factory.create_ssh.return_value = mock_connector

        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_connection.return_value = orm_node

        svc = NodeCommandService(
            node_reader=repo,
            status_writer=repo,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=factory,
        )
        await svc.execute_command(
            node_response.id,
            CommandRequestDTO(command="uptime", timeout=30),
        )
        _, kwargs = factory.create_ssh.call_args
        assert kwargs["timeout"] == 30

    async def test_audit_log_called(self) -> None:
        repo = AsyncMock()
        factory = MagicMock()
        mock_connector = AsyncMock()
        mock_connector.execute_command.return_value = ("ok", "", 0)
        mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
        mock_connector.__aexit__ = AsyncMock(return_value=False)
        factory.create_ssh.return_value = mock_connector

        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_connection.return_value = orm_node

        audit = AsyncMock()
        svc = NodeCommandService(
            node_reader=repo,
            status_writer=repo,
            credential_cipher=AesGcmCredentialCipher(),
            connector_factory=factory,
            audit_service=audit,
        )
        await svc.execute_command(
            node_response.id,
            CommandRequestDTO(command="uptime"),
        )
        audit.log_required.assert_awaited_once()
