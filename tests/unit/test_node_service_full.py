"""Full coverage tests for NodeService."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NodeNotFoundError
from app.core.security import decrypt, encrypt
from app.repositories.node_repo import NodeRepository
from app.schemas.node import NodeCreate, NodeUpdate
from app.services.node_service import NodeService


def _make_orm_node(**overrides: Any) -> Any:
    from app.models.node import NodeModel

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
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return NodeModel(**defaults)


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock(spec=NodeRepository)


@pytest.fixture
def service(repo: AsyncMock) -> NodeService:
    return NodeService(repository=repo)


class TestGetNode:
    @pytest.mark.asyncio
    async def test_found(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = _make_orm_node()
        repo.get_by_id.return_value = orm_node
        result = await service.get_node(orm_node.id)
        assert result.name == "server-1"

    @pytest.mark.asyncio
    async def test_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.get_node(uuid.uuid4())


class TestGetAllNodes:
    @pytest.mark.asyncio
    async def test_empty(self, service: NodeService, repo: AsyncMock) -> None:
        repo.get_all.return_value = []
        repo.count.return_value = 0
        nodes, total = await service.get_all_nodes()
        assert nodes == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_with_data(self, service: NodeService, repo: AsyncMock) -> None:
        nodes = [_make_orm_node(name="n1"), _make_orm_node(name="n2")]
        repo.get_all.return_value = nodes
        repo.count.return_value = 2
        result_nodes, total = await service.get_all_nodes()
        assert len(result_nodes) == 2
        assert total == 2


class TestCreateNode:
    @pytest.mark.asyncio
    async def test_creates_node(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = _make_orm_node()
        repo.create.return_value = orm_node
        data = NodeCreate(name="test", host="1.2.3.4", connection_type="ssh")
        result = await service.create_node(data)
        assert result.name == "server-1"
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_encrypts_password(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        orm_node = _make_orm_node()
        repo.create.return_value = orm_node
        data = NodeCreate(
            name="test",
            host="1.2.3.4",
            connection_type="ssh",
            password="secret123",
        )
        await service.create_node(data)
        call_data = repo.create.call_args[0][0]
        assert call_data["password"] != "secret123"
        assert decrypt(call_data["password"]) == "secret123"

    @pytest.mark.asyncio
    async def test_encrypts_ssh_key(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        orm_node = _make_orm_node()
        repo.create.return_value = orm_node
        key = "-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----"
        data = NodeCreate(
            name="test",
            host="1.2.3.4",
            connection_type="ssh",
            ssh_key=key,
        )
        await service.create_node(data)
        call_data = repo.create.call_args[0][0]
        assert "BEGIN" not in call_data["ssh_key"]


class TestUpdateNode:
    @pytest.mark.asyncio
    async def test_found(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = _make_orm_node()
        repo.update.return_value = orm_node
        data = NodeUpdate(name="updated")
        result = await service.update_node(orm_node.id, data)
        assert result.name == "server-1"

    @pytest.mark.asyncio
    async def test_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.update.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.update_node(uuid.uuid4(), NodeUpdate(name="x"))

    @pytest.mark.asyncio
    async def test_encrypts_fields(self, service: NodeService, repo: AsyncMock) -> None:
        orm_node = _make_orm_node()
        repo.update.return_value = orm_node
        data = NodeUpdate(password="newpass")
        await service.update_node(orm_node.id, data)
        call_data = repo.update.call_args[0][1]
        assert call_data["password"] != "newpass"


class TestDeleteNode:
    @pytest.mark.asyncio
    async def test_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.delete.return_value = True
        result = await service.delete_node(uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_not_found(self, service: NodeService, repo: AsyncMock) -> None:
        repo.delete.return_value = False
        with pytest.raises(NodeNotFoundError):
            await service.delete_node(uuid.uuid4())


class TestDecryptValue:
    def test_none_returns_none(self) -> None:
        assert NodeService._decrypt_value(None) is None

    def test_empty_string_returns_empty(self) -> None:
        assert NodeService._decrypt_value("") == ""

    def test_encrypted_value_decrypts(self) -> None:
        token = encrypt("secret")
        assert NodeService._decrypt_value(token) == "secret"

    def test_non_encrypted_value_returns_as_is(self) -> None:
        assert NodeService._decrypt_value("plain-text") == "plain-text"


class TestCheckConnectivityEdgeCases:
    @pytest.mark.asyncio
    async def test_orm_node_not_found_after_get_node(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        """When get_node succeeds but ORM node is gone (race condition)."""
        orm_node = _make_orm_node()
        repo.get_by_id.side_effect = [orm_node, None]
        with pytest.raises(NodeNotFoundError):
            await service.check_connectivity(orm_node.id)


class TestExecuteCommandEdgeCases:
    @pytest.mark.asyncio
    async def test_orm_node_not_found_after_get_node(
        self, service: NodeService, repo: AsyncMock
    ) -> None:
        """When get_node succeeds but ORM node is gone (race condition)."""
        orm_node = _make_orm_node()
        repo.get_by_id.side_effect = [orm_node, None]
        with pytest.raises(NodeNotFoundError):
            from app.schemas.node import CommandRequest

            await service.execute_command(orm_node.id, CommandRequest(command="ls"))
