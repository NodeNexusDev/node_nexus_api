"""Unit tests for node tags functionality."""

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NodeNotFoundError
from app.models.node import NodeModel
from app.repositories.node_repo import NodeRepository
from app.schemas.node import NodeCreate, TagAdd, TagRemove
from app.services.node_management_service import NodeManagementService


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
        "docker_host": None,
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
def service(repo: AsyncMock) -> NodeManagementService:
    return NodeManagementService(repository=repo)


class TestGetNodesByTags:
    async def test_filters_by_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        nodes = [_make_orm_node(tags=["prod", "web"])]
        repo.get_by_tags.return_value = nodes
        repo.count_by_tags.return_value = 1
        result_nodes, total = await service.get_nodes_by_tags(["prod"])
        assert len(result_nodes) == 1
        assert total == 1

    async def test_empty_result(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_by_tags.return_value = []
        repo.count_by_tags.return_value = 0
        result_nodes, total = await service.get_nodes_by_tags(["nonexistent"])
        assert result_nodes == []
        assert total == 0


class TestGetAllTags:
    async def test_returns_unique_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_all_tags.return_value = ["prod", "staging", "web"]
        tags = await service.get_all_tags()
        assert tags == ["prod", "staging", "web"]

    async def test_empty_when_no_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_all_tags.return_value = []
        tags = await service.get_all_tags()
        assert tags == []


class TestAddTag:
    async def test_adds_tag_to_node(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = _make_orm_node(tags=[])
        updated_node = _make_orm_node(tags=["prod"])
        repo.get_by_id.return_value = node
        repo.update.return_value = updated_node
        result = await service.add_tag(node.id, TagAdd(tag="prod"))
        assert result.tags == ("prod",)
        repo.update.assert_called_once_with(node.id, {"tags": ["prod"]})

    async def test_does_not_duplicate_tag(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = _make_orm_node(tags=["prod"])
        repo.get_by_id.return_value = node
        result = await service.add_tag(node.id, TagAdd(tag="prod"))
        assert result.tags == ("prod",)
        repo.update.assert_not_called()

    async def test_node_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.add_tag(uuid.uuid4(), TagAdd(tag="prod"))


class TestRemoveTag:
    async def test_removes_tag_from_node(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = _make_orm_node(tags=["prod", "web"])
        updated_node = _make_orm_node(tags=["web"])
        repo.get_by_id.return_value = node
        repo.update.return_value = updated_node
        result = await service.remove_tag(node.id, TagRemove(tag="prod"))
        assert result.tags == ("web",)
        repo.update.assert_called_once_with(node.id, {"tags": ["web"]})

    async def test_noop_when_tag_absent(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = _make_orm_node(tags=["web"])
        repo.get_by_id.return_value = node
        result = await service.remove_tag(node.id, TagRemove(tag="prod"))
        assert result.tags == ("web",)
        repo.update.assert_not_called()

    async def test_node_not_found(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        repo.get_by_id.return_value = None
        with pytest.raises(NodeNotFoundError):
            await service.remove_tag(uuid.uuid4(), TagRemove(tag="prod"))


class TestTagsInCreate:
    async def test_create_with_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = _make_orm_node(tags=["prod", "web"])
        repo.create.return_value = node
        data = NodeCreate(
            name="test",
            host="1.2.3.4",
            connection_type="ssh",
            tags=["prod", "web"],
        )
        result = await service.create_node(data)
        assert result.tags == ("prod", "web")
        call_data = repo.create.call_args[0][0]
        assert call_data["tags"] == ["prod", "web"]

    async def test_create_without_tags(
        self, service: NodeManagementService, repo: AsyncMock
    ) -> None:
        node = _make_orm_node(tags=[])
        repo.create.return_value = node
        data = NodeCreate(name="test", host="1.2.3.4", connection_type="ssh")
        result = await service.create_node(data)
        assert result.tags == ()
