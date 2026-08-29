"""Service for refreshing SSH host keys."""

from uuid import UUID

import structlog

from app.application.dto.node_view import NodeViewDTO
from app.application.ports.known_hosts import KnownHostsManager
from app.application.ports.node_management import NodeManagementReader
from app.core.exceptions import HostKeyFetchError, NodeNotFoundError

audit = structlog.get_logger("audit")
logger = structlog.get_logger()


class NodeHostKeyService:
    """Refresh known_hosts entry for a persisted node."""

    def __init__(
        self,
        reader: NodeManagementReader,
        known_hosts: KnownHostsManager,
    ) -> None:
        self._reader = reader
        self._known_hosts = known_hosts

    async def refresh_host_key(self, node_id: UUID) -> NodeViewDTO:
        """Fetch and refresh host key for the node.

        Raises:
            NodeNotFoundError: if node does not exist.
            HostKeyFetchError: if key cannot be fetched.
        """
        node = await self._reader.get_node(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")
        host = node.endpoint.host
        port = node.endpoint.port
        logger.info(
            "host_key.refresh.start",
            node_id=str(node_id),
            host=host,
            port=port,
        )
        try:
            await self._known_hosts.refresh_host(host, port)
        except HostKeyFetchError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = f"Failed to refresh host key for {host}:{port}: {exc}"
            raise HostKeyFetchError(msg) from exc
        audit.info("host_key.refresh.ok", node_id=str(node_id), host=host, port=port)
        return node
