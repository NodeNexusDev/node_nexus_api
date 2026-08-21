"""Shared target resolution logic for bulk operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.ports.node_reader import NodeConnectionReader


async def resolve_targets(
    node_reader: NodeConnectionReader,
    node_ids: frozenset[Any] | tuple[Any, ...] | list[Any] | None = None,
    tags: frozenset[Any] | tuple[Any, ...] | list[Any] | None = None,
) -> list[NodeConnectionDTO]:
    """Resolve target nodes from IDs and tags with intersection logic.

    When both node_ids and tags are provided, only nodes matching BOTH
    criteria are returned (AND/intersection). This ensures precise targeting
    for node bulk operations.

    For docker bulk operations, see DockerBulkService._resolve_node_ids()
    which uses union (OR) logic to expand the target set.
    """
    nodes_by_ids = None
    if node_ids:
        nodes_by_ids = await node_reader.get_connections_by_ids(list(node_ids))

    nodes_by_tags = None
    if tags:
        nodes_by_tags = await node_reader.get_connections_by_tags(list(tags))

    if nodes_by_ids is not None and nodes_by_tags is not None:
        tag_ids = {node.id for node in nodes_by_tags}
        return [node for node in nodes_by_ids if node.id in tag_ids]
    if nodes_by_ids is not None:
        return nodes_by_ids
    return nodes_by_tags or []
