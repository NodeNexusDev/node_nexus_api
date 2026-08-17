"""Tests for shared target resolution logic."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.adapters.persistence.dao.base import escape_ilike
from app.application.services._target_resolver import resolve_targets


@pytest.fixture
def reader():
    return AsyncMock()


async def test_resolve_by_ids_only(reader):
    node_id = uuid4()
    reader.get_connections_by_ids.return_value = [MagicMock(id=node_id)]
    result = await resolve_targets(reader, node_ids=frozenset({node_id}))
    assert len(result) == 1
    reader.get_connections_by_ids.assert_awaited_once_with([node_id])


async def test_resolve_by_tags_only(reader):
    node_id = uuid4()
    reader.get_connections_by_tags.return_value = [MagicMock(id=node_id)]
    result = await resolve_targets(reader, tags=frozenset({"web"}))
    assert len(result) == 1


async def test_resolve_intersection(reader):
    id_node = MagicMock(id=uuid4())
    tag_node = MagicMock(id=uuid4())
    reader.get_connections_by_ids.return_value = [id_node, tag_node]
    reader.get_connections_by_tags.return_value = [id_node]
    result = await resolve_targets(
        reader,
        node_ids=frozenset({id_node.id, tag_node.id}),
        tags=frozenset({"web"}),
    )
    assert result == [id_node]


async def test_resolve_empty(reader):
    result = await resolve_targets(reader)
    assert result == []


def test_escape_ilike():
    assert escape_ilike("100%") == "100\\%"
    assert escape_ilike("test_value") == "test\\_value"
    assert escape_ilike("normal") == "normal"
    assert escape_ilike("%_\\") == "\\%\\_\\\\"
