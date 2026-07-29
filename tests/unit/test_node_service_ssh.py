"""Unit tests for focused node SSH services."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.dto.command_execution import CommandRequestDTO
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.security import decrypt, encrypt
from app.repositories.node_repo import NodeRepository
from app.services.node_bulk_command_service import NodeBulkCommandService
from app.services.node_command_service import NodeCommandService
from tests.unit.conftest import make_orm_node, make_response


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=NodeRepository)


@pytest.fixture
def mock_factory() -> MagicMock:
    factory = MagicMock()
    mock_connector = AsyncMock()
    mock_connector.execute_command.return_value = ("ok", "", 0)
    mock_connector.__aenter__ = AsyncMock(return_value=mock_connector)
    mock_connector.__aexit__ = AsyncMock(return_value=False)
    factory.create_ssh.return_value = mock_connector
    return factory


@pytest.fixture
def service(repo: AsyncMock, mock_factory: MagicMock) -> NodeCommandService:
    return NodeCommandService(
        repository=repo,
        connector_factory=mock_factory,
    )


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        secret = "my-super-secret-key"
        token = encrypt(secret)
        assert token != secret
        assert decrypt(token) == secret

    def test_encrypt_produces_different_ciphertext(self) -> None:
        token1 = encrypt("same-value")
        token2 = encrypt("same-value")
        assert token1 != token2


class TestCheckConnectivity:
    async def test_sets_active_on_success(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_by_id.return_value = orm_node
        repo.update.return_value = orm_node

        result = await service.check_connectivity(node_response.id)

        assert result.status == "active"
        repo.update.assert_called_once_with(node_response.id, {"status": "active"})
        mock_factory.create_ssh.assert_called_once_with(
            host=node_response.host,
            port=node_response.port,
            username=node_response.username,
            password=None,
            ssh_key=None,
        )

    async def test_sets_unreachable_on_failure(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        unreachable_node = make_orm_node(id=node_response.id, status="unreachable")
        repo.get_by_id.return_value = orm_node
        repo.update.return_value = unreachable_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(side_effect=Exception("timeout"))

        result = await service.check_connectivity(node_response.id)

        assert result.status == "unreachable"

    async def test_node_not_found(
        self, service: NodeCommandService, repo: AsyncMock
    ) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.check_connectivity(uuid.uuid4())


class TestExecuteCommand:
    async def test_returns_result(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_by_id.return_value = orm_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("uptime\n12:00", "", 0)

        result = await service.execute_command(
            node_response.id, CommandRequestDTO(command="uptime")
        )

        assert result.stdout == "uptime\n12:00"
        assert result.stderr == ""
        assert result.exit_code == 0
        mock_connector.execute_command.assert_called_once_with("uptime")

    async def test_raises_on_connection_error(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_by_id.return_value = orm_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(side_effect=Exception("refused"))

        with pytest.raises(ConnectionFailedError):
            await service.execute_command(
                node_response.id, CommandRequestDTO(command="ls")
            )

    async def test_node_not_found(
        self, service: NodeCommandService, repo: AsyncMock
    ) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.execute_command(
                uuid.uuid4(),
                CommandRequestDTO(command="ls"),
            )


class TestCheckConnectivityConnectionFailed:
    async def test_sets_unreachable_on_connection_failed(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        unreachable_node = make_orm_node(id=node_response.id, status="unreachable")
        repo.get_by_id.return_value = orm_node
        repo.update.return_value = unreachable_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(
            side_effect=ConnectionFailedError("Connection refused")
        )

        result = await service.check_connectivity(node_response.id)

        assert result.status == "unreachable"
        repo.update.assert_called_once_with(node_response.id, {"status": "unreachable"})


class TestExecuteCommandConnectionFailed:
    async def test_raises_connection_failed(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = make_response()
        orm_node = make_orm_node(id=node_response.id)
        repo.get_by_id.return_value = orm_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(
            side_effect=ConnectionFailedError("Connection refused")
        )

        with pytest.raises(ConnectionFailedError):
            await service.execute_command(
                node_response.id, CommandRequestDTO(command="ls")
            )


class TestBulkExecuteConnectionFailed:
    async def test_returns_error_result(
        self, service: NodeCommandService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        orm_node = make_orm_node()
        repo.get_by_id.return_value = orm_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(
            side_effect=ConnectionFailedError("Connection refused")
        )

        bulk_service = NodeBulkCommandService(
            repository=repo,
            connector_factory=mock_factory,
        )
        result = await bulk_service._execute_on_single_node(
            orm_node,
            "echo hi",
        )

        assert result.exit_code == 1
        assert result.stdout == ""
        assert "Connection refused" in result.stderr
