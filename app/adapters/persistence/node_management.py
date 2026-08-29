"""Short-scope SQLAlchemy adapter for node management ports."""

from typing import cast
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.persistence.dao.node import NodeRepository
from app.application.dto.node_management import (
    NodeCreateDTO,
    NodeCursorPageDTO,
    NodeCursorQueryDTO,
    NodeListQueryDTO,
    NodePageDTO,
    NodeUpdateDTO,
)
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeEndpoint
from app.core.exceptions import NodeNameConflictError
from app.core.types import ConnectionType, NodeStatus
from app.models.node import NodeModel


class SqlAlchemyNodeManagementGateway:
    """Implement node management ports with operation-local sessions."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_node(self, node_id: UUID) -> NodeViewDTO | None:
        """Return one node outside the persistence scope."""
        async with self._sessionmaker() as session:
            node = await NodeRepository(session).get_by_id(node_id)
            return self._to_view(node) if node is not None else None

    async def list_nodes(self, query: NodeListQueryDTO) -> NodePageDTO:
        """Return one offset-based page outside the persistence scope."""
        tags = list(query.tags) or None
        async with self._sessionmaker() as session:
            repository = NodeRepository(session)
            if tags or query.search:
                nodes = await repository.get_filtered(
                    tags=tags,
                    search=query.search,
                    skip=query.offset,
                    limit=query.limit,
                )
                total = await repository.count_filtered(
                    tags=tags,
                    search=query.search,
                )
            else:
                nodes = await repository.get_all(
                    skip=query.offset,
                    limit=query.limit,
                )
                total = await repository.count()
            return NodePageDTO(
                items=tuple(self._to_view(node) for node in nodes),
                total=total,
            )

    async def list_nodes_cursor(self, query: NodeCursorQueryDTO) -> NodeCursorPageDTO:
        """Return one keyset-based page outside the persistence scope."""
        async with self._sessionmaker() as session:
            nodes = await NodeRepository(session).get_list_cursor(
                cursor=query.cursor,
                limit=query.limit,
                tags=list(query.tags) or None,
                search=query.search,
            )
            has_more = len(nodes) > query.limit
            items = nodes[: query.limit]
            next_cursor = (
                (items[-1].created_at, items[-1].id) if has_more and items else None
            )
            return NodeCursorPageDTO(
                items=tuple(self._to_view(node) for node in items),
                next_cursor=next_cursor,
                has_more=has_more,
            )

    async def list_tags(self) -> list[str]:
        """Return all unique node tags."""
        async with self._sessionmaker() as session:
            return await NodeRepository(session).get_all_tags()

    async def create_node(self, data: NodeCreateDTO) -> NodeViewDTO:
        """Create a node in one short transaction."""
        try:
            async with self._sessionmaker.begin() as session:
                node = await NodeRepository(session).create(
                    {
                        "name": data.name,
                        "host": data.endpoint.host,
                        "port": data.endpoint.port,
                        "connection_type": data.endpoint.connection_type,
                        "username": data.credentials.username,
                        "password": data.credentials.password,
                        "ssh_key": data.credentials.ssh_key,
                        "passphrase": data.credentials.passphrase,
                        "docker_host": data.endpoint.docker_host,
                        "has_docker": bool(data.endpoint.has_docker),
                        "tags": list(data.tags),
                    }
                )
                return self._to_view(node)
        except IntegrityError as exc:
            raise NodeNameConflictError(
                f"Node name '{data.name}' already exists"
            ) from exc

    async def update_node(
        self, node_id: UUID, data: NodeUpdateDTO
    ) -> NodeViewDTO | None:
        """Update a node in one short transaction."""
        changes: dict[str, object] = dict(data.changes)
        tags = changes.get("tags")
        if isinstance(tags, tuple):
            changes["tags"] = list(tags)
        async with self._sessionmaker.begin() as session:
            node = await NodeRepository(session).update(node_id, changes)
            return self._to_view(node) if node is not None else None

    async def delete_node(self, node_id: UUID) -> bool:
        """Delete a node in one short transaction."""
        async with self._sessionmaker.begin() as session:
            repository = NodeRepository(session)
            node = await repository.get_by_id(node_id)
            if node is None:
                return False
            await session.delete(node)
            await session.flush()
            return True

    async def update_node_status(
        self, node_id: UUID, status: str
    ) -> NodeViewDTO | None:
        """Persist connectivity status in one short transaction."""
        async with self._sessionmaker.begin() as session:
            node = await NodeRepository(session).update(
                node_id,
                {"status": status},
            )
            return self._to_view(node) if node is not None else None

    @staticmethod
    def _to_view(node: NodeModel) -> NodeViewDTO:
        """Map an ORM node to public-safe application data."""
        has_docker = bool(getattr(node, "has_docker", False))
        return NodeViewDTO(
            id=node.id,
            name=node.name,
            endpoint=NodeEndpoint(
                host=node.host,
                port=node.port,
                connection_type=cast(ConnectionType, node.connection_type),
                docker_host=node.docker_host,
                has_docker=has_docker,
            ),
            status=cast(NodeStatus, node.status),
            username=node.username,
            tags=tuple(node.tags or ()),
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
