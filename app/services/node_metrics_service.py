"""System metrics collection use case for one node."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from app.application.ports.node_reader import NodeConnectionReader
    from app.core.connectors.base import ConnectorFactory

from app.core.exceptions import ConnectionFailedError, NodeNotFoundError
from app.core.ssh_utils import decrypt_value, get_connector_factory
from app.repositories.node_repo import NodeRepository
from app.schemas.node import CpuMetrics, DiskMetrics, MemoryMetrics, NodeMetrics

audit = structlog.get_logger("audit")


class NodeMetricsService:
    """Collect CPU, memory, disk, and uptime metrics through SSH."""

    def __init__(
        self,
        repository: NodeRepository,
        connector_factory: ConnectorFactory | None = None,
        node_reader: NodeConnectionReader | None = None,
    ) -> None:
        self._repository = repository
        self._connector_factory = connector_factory
        self._node_reader = node_reader

    async def collect(self, node_id: UUID) -> NodeMetrics:
        """Collect current system metrics from a node."""
        node = (
            await self._node_reader.get_connection(node_id)
            if self._node_reader
            else await self._repository.get_by_id(node_id)
        )
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        connector = get_connector_factory(self._connector_factory).create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=decrypt_value(node.password),
            ssh_key=decrypt_value(node.ssh_key),
        )

        try:
            async with connector:
                cpu_usage, cores = await self._collect_cpu(connector)
                mem_total, mem_used, mem_percent = await self._collect_usage(
                    connector,
                    "free -b | awk '/Mem:/ {print $2, $3, $4}'",
                )
                disk_total, disk_used, disk_percent = await self._collect_usage(
                    connector,
                    "df -B1 / | awk 'NR==2 {print $2, $3, $4}'",
                )
                uptime_stdout, _, _ = await connector.execute_command("uptime -s")

            audit.info("node.metrics.collected", node_id=str(node_id))
            return NodeMetrics(
                cpu=CpuMetrics(usage_percent=cpu_usage, cores=cores),
                memory=MemoryMetrics(
                    total_bytes=mem_total,
                    used_bytes=mem_used,
                    percent=round(mem_percent, 2),
                ),
                disk=DiskMetrics(
                    total_bytes=disk_total,
                    used_bytes=disk_used,
                    percent=round(disk_percent, 2),
                ),
                uptime_since=uptime_stdout.strip() or "unknown",
            )
        except ConnectionFailedError as exc:
            audit.error("node.metrics.failed", node_id=str(node_id), error=str(exc))
            raise
        except Exception as exc:
            audit.error(
                "node.metrics.unexpected_error",
                node_id=str(node_id),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise ConnectionFailedError(
                f"Failed to collect metrics from node {node_id}: {exc}"
            ) from exc

    async def get_node_metrics(self, node_id: UUID) -> NodeMetrics:
        """Expose the stable node API use-case name."""
        return await self.collect(node_id)

    @staticmethod
    async def _collect_cpu(connector) -> tuple[float, int]:  # noqa: ANN001
        cpu_stdout, _, _ = await connector.execute_command(
            "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'"
        )
        cores_stdout, _, _ = await connector.execute_command("nproc")
        cpu_usage = float(cpu_stdout.strip()) if cpu_stdout.strip() else 0.0
        cores = int(cores_stdout.strip()) if cores_stdout.strip() else 1
        return cpu_usage, cores

    @staticmethod
    async def _collect_usage(
        connector,  # noqa: ANN001
        command: str,
    ) -> tuple[int, int, float]:
        stdout, _, _ = await connector.execute_command(command)
        parts = stdout.strip().split()
        if len(parts) < 3:
            return 0, 0, 0.0
        total = int(parts[0])
        used = int(parts[1])
        percent = (used / total * 100) if total > 0 else 0.0
        return total, used, percent
