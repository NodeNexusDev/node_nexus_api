"""Unit tests for NodeService SSH integration."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.security import decrypt, encrypt
from app.models.node import NodeModel
from app.repositories.node_repo import NodeRepository
from app.schemas.node import CommandRequest, NodeResponse
from app.services.node_service import NodeService


def _make_response(**overrides: Any) -> NodeResponse:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeResponse(**defaults)


def _make_orm_node(**overrides: Any) -> NodeModel:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "server-1",
        "host": "10.0.0.1",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "root",
        "password": None,
        "ssh_key": None,
        "tags": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


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
def service(repo: AsyncMock, mock_factory: MagicMock) -> NodeService:
    return NodeService(repository=repo, connector_factory=mock_factory)


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
    @pytest.mark.asyncio
    async def test_sets_active_on_success(
        self, service: NodeService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = _make_response()
        orm_node = _make_orm_node(id=node_response.id)
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

    @pytest.mark.asyncio
    async def test_sets_unreachable_on_failure(
        self, service: NodeService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = _make_response()
        orm_node = _make_orm_node(id=node_response.id)
        unreachable_node = _make_orm_node(id=node_response.id, status="unreachable")
        repo.get_by_id.return_value = orm_node
        repo.update.return_value = unreachable_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(side_effect=Exception("timeout"))

        result = await service.check_connectivity(node_response.id)

        assert result.status == "unreachable"

    @pytest.mark.asyncio
    async def test_node_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.check_connectivity(uuid.uuid4())


class TestExecuteCommand:
    @pytest.mark.asyncio
    async def test_returns_result(
        self, service: NodeService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = _make_response()
        orm_node = _make_orm_node(id=node_response.id)
        repo.get_by_id.return_value = orm_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.execute_command.return_value = ("uptime\n12:00", "", 0)

        result = await service.execute_command(
            node_response.id, CommandRequest(command="uptime")
        )

        assert result.stdout == "uptime\n12:00"
        assert result.stderr == ""
        assert result.exit_code == 0
        mock_connector.execute_command.assert_called_once_with("uptime")

    @pytest.mark.asyncio
    async def test_raises_on_connection_error(
        self, service: NodeService, repo: AsyncMock, mock_factory: MagicMock
    ) -> None:
        node_response = _make_response()
        orm_node = _make_orm_node(id=node_response.id)
        repo.get_by_id.return_value = orm_node

        mock_connector = mock_factory.create_ssh.return_value
        mock_connector.__aenter__ = AsyncMock(side_effect=Exception("refused"))

        with pytest.raises(ConnectionFailedError):
            await service.execute_command(
                node_response.id, CommandRequest(command="ls")
            )

    @pytest.mark.asyncio
    async def test_node_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.execute_command(uuid.uuid4(), CommandRequest(command="ls"))
