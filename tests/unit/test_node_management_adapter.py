"""Tests for the SQLAlchemy node management adapter."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.adapters.persistence.node_management import (
    SqlAlchemyNodeManagementGateway,
)
from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeListQueryDTO,
    NodeUpdateDTO,
)
from app.core.exceptions import NodeNameConflictError
from tests.unit.conftest import make_orm_node


def _sessionmaker() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    factory = MagicMock()
    factory.return_value = context
    factory.begin.return_value = context
    return factory, session


async def test_get_node_maps_orm_to_public_dto() -> None:
    factory, _ = _sessionmaker()
    node = make_orm_node(password="encrypted", ssh_key="encrypted-key")

    with patch(
        "app.adapters.persistence.node_management.NodeRepository"
    ) as repository_type:
        repository_type.return_value.get_by_id = AsyncMock(return_value=node)
        result = await SqlAlchemyNodeManagementGateway(factory).get_node(node.id)

    assert result is not None
    assert result.id == node.id
    assert result.tags == ()
    assert not hasattr(result, "password")


async def test_list_nodes_maps_page_and_query() -> None:
    factory, _ = _sessionmaker()
    node = make_orm_node(tags=["prod"])

    with patch(
        "app.adapters.persistence.node_management.NodeRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.get_filtered = AsyncMock(return_value=[node])
        repository.count_filtered = AsyncMock(return_value=1)
        result = await SqlAlchemyNodeManagementGateway(factory).list_nodes(
            NodeListQueryDTO(
                offset=20,
                limit=10,
                tags=("prod",),
                search="server",
            )
        )

    assert result.items[0].id == node.id
    assert result.total == 1
    repository.get_filtered.assert_awaited_once_with(
        tags=["prod"],
        search="server",
        skip=20,
        limit=10,
    )


async def test_create_node_uses_short_transaction_and_maps_result() -> None:
    factory, _ = _sessionmaker()
    node = make_orm_node()
    data = NodeCreateDTO(
        name="node",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
        password="encrypted",
        tags=("prod",),
    )

    with patch(
        "app.adapters.persistence.node_management.NodeRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.create = AsyncMock(return_value=node)
        result = await SqlAlchemyNodeManagementGateway(factory).create_node(data)

    assert result.id == node.id
    factory.begin.assert_called_once_with()
    persisted = repository.create.call_args.args[0]
    assert persisted["password"] == "encrypted"
    assert persisted["tags"] == ["prod"]


async def test_create_node_maps_unique_violation_to_domain_error() -> None:
    factory, _ = _sessionmaker()
    data = NodeCreateDTO(
        name="duplicate",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
    )

    with patch(
        "app.adapters.persistence.node_management.NodeRepository"
    ) as repository_type:
        repository_type.return_value.create = AsyncMock(
            side_effect=IntegrityError("insert", {}, Exception("unique"))
        )
        with pytest.raises(NodeNameConflictError, match="duplicate"):
            await SqlAlchemyNodeManagementGateway(factory).create_node(data)


async def test_update_node_normalizes_immutable_tags() -> None:
    factory, _ = _sessionmaker()
    node = make_orm_node(tags=["prod"])
    node_id = uuid.uuid4()

    with patch(
        "app.adapters.persistence.node_management.NodeRepository"
    ) as repository_type:
        repository = repository_type.return_value
        repository.update = AsyncMock(return_value=node)
        result = await SqlAlchemyNodeManagementGateway(factory).update_node(
            node_id,
            NodeUpdateDTO(changes=(("tags", ("prod",)),)),
        )

    assert result is not None
    repository.update.assert_awaited_once_with(node_id, {"tags": ["prod"]})


async def test_delete_node_uses_adapter_owned_transaction() -> None:
    factory, session = _sessionmaker()
    node = make_orm_node()

    with patch(
        "app.adapters.persistence.node_management.NodeRepository"
    ) as repository_type:
        repository_type.return_value.get_by_id = AsyncMock(return_value=node)
        deleted = await SqlAlchemyNodeManagementGateway(factory).delete_node(node.id)

    assert deleted is True
    session.delete.assert_awaited_once_with(node)
    session.flush.assert_awaited_once_with()
