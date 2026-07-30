"""Unit tests for node tags functionality."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.adapters.security import AesGcmCredentialCipher
from app.application.dto.node_management import (
    NodeCreateDTO,
    NodePageDTO,
    NodeTagDTO,
)
from app.application.services.node_management_service import NodeManagementService
from app.core.exceptions import NodeNotFoundError
from tests.unit.conftest import make_node_view


@pytest.fixture
def repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(repo: AsyncMock) -> NodeManagementService:
    return NodeManagementService(
        reader=repo, writer=repo, credential_cipher=AesGcmCredentialCipher()
    )


class TestGetNodesByTags:
    async def test_filters_by_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        nodes = (make_node_view(tags=["prod", "web"]),)
        repo.list_nodes.return_value = NodePageDTO(items=nodes, total=1)
        result_nodes, total = await service.get_nodes_by_tags(["prod"])
        assert len(result_nodes) == 1
        assert total == 1

    async def test_empty_result(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.list_nodes.return_value = NodePageDTO(items=(), total=0)
        result_nodes, total = await service.get_nodes_by_tags(["nonexistent"])
        assert result_nodes == []
        assert total == 0


class TestGetAllTags:
    async def test_returns_unique_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.list_tags.return_value = ["prod", "staging", "web"]
        tags = await service.get_all_tags()
        assert tags == ["prod", "staging", "web"]

    async def test_empty_when_no_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.list_tags.return_value = []
        tags = await service.get_all_tags()
        assert tags == []


class TestAddTag:
    async def test_adds_tag_to_node(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view(tags=[])
        updated_node = make_node_view(tags=["prod"])
        repo.get_node.return_value = node
        repo.update_node.return_value = updated_node
        result = await service.add_tag(node.id, NodeTagDTO(tag="prod"))
        assert result.tags == ("prod",)
        changes = repo.update_node.call_args.args[1]
        assert dict(changes.changes) == {"tags": ("prod",)}

    async def test_does_not_duplicate_tag(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view(tags=["prod"])
        repo.get_node.return_value = node
        result = await service.add_tag(node.id, NodeTagDTO(tag="prod"))
        assert result.tags == ("prod",)
        repo.update_node.assert_not_called()

    async def test_node_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_node.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.add_tag(uuid.uuid4(), NodeTagDTO(tag="prod"))


class TestRemoveTag:
    async def test_removes_tag_from_node(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view(tags=["prod", "web"])
        updated_node = make_node_view(tags=["web"])
        repo.get_node.return_value = node
        repo.update_node.return_value = updated_node
        result = await service.remove_tag(node.id, NodeTagDTO(tag="prod"))
        assert result.tags == ("web",)
        changes = repo.update_node.call_args.args[1]
        assert dict(changes.changes) == {"tags": ("web",)}

    async def test_noop_when_tag_absent(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view(tags=["web"])
        repo.get_node.return_value = node
        result = await service.remove_tag(node.id, NodeTagDTO(tag="prod"))
        assert result.tags == ("web",)
        repo.update_node.assert_not_called()

    async def test_node_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_node.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.remove_tag(uuid.uuid4(), NodeTagDTO(tag="prod"))


class TestTagsInCreate:
    async def test_create_with_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view(tags=["prod", "web"])
        repo.create_node.return_value = node
        data = NodeCreateDTO(
            name="test",
            host="1.2.3.4",
            port=22,
            connection_type="ssh",
            tags=("prod", "web"),
        )
        result = await service.create_node(data)
        assert result.tags == ("prod", "web")
        call_data = repo.create_node.call_args.args[0]
        assert call_data.tags == ("prod", "web")

    async def test_create_without_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = make_node_view(tags=[])
        repo.create_node.return_value = node
        data = NodeCreateDTO(
            name="test", host="1.2.3.4", port=22, connection_type="ssh"
        )
        result = await service.create_node(data)
        assert result.tags == ()
