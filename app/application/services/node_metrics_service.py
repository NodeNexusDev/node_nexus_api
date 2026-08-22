"""System metrics collection use case for one node."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_reader import NodeConnectionReader
    from app.application.ports.remote_command import (
        RemoteCommandSession,
        RemoteConnectorFactory,
    )

from app.application.dto.node_metrics import (
    CpuMetricsDTO,
    LoadAverageDTO,
    NodeMetricsDTO,
    UsageMetricsDTO,
)
from app.core.exceptions import ConnectionFailedError, NodeNotFoundError

audit = structlog.get_logger("audit")


class NodeMetricsService:
    """Collect CPU, memory, disk, and uptime metrics through SSH."""

    def __init__(
        self,
        node_reader: NodeConnectionReader,
        credential_cipher: CredentialCipher,
        connector_factory: RemoteConnectorFactory,
    ) -> None:
        self._connector_factory = connector_factory
        self._node_reader = node_reader
        self._credential_cipher = credential_cipher

    async def collect(self, node_id: UUID) -> NodeMetricsDTO:
        """Collect current system metrics from a node."""
        node = await self._node_reader.get_connection(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} not found")

        connector = self._connector_factory.create_ssh(
            host=node.host,
            port=node.port,
            username=node.username,
            password=self._credential_cipher.decrypt(node.password),
            ssh_key=self._credential_cipher.decrypt(node.ssh_key),
            passphrase=self._credential_cipher.decrypt(node.passphrase),
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
                load_average = await self._collect_load_average(connector)
                uptime_stdout, _, _ = await connector.execute_command("uptime -s")

            audit.info("node.metrics.collected", node_id=str(node_id))
            return NodeMetricsDTO(
                cpu=CpuMetricsDTO(usage_percent=cpu_usage, cores=cores),
                memory=UsageMetricsDTO(
                    total_bytes=mem_total,
                    used_bytes=mem_used,
                    percent=round(mem_percent, 2),
                ),
                disk=UsageMetricsDTO(
                    total_bytes=disk_total,
                    used_bytes=disk_used,
                    percent=round(disk_percent, 2),
                ),
                load_average=load_average,
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

    async def get_node_metrics(self, node_id: UUID) -> NodeMetricsDTO:
        """Expose the stable node API use-case name."""
        return await self.collect(node_id)

    @staticmethod
    async def _collect_cpu(connector: RemoteCommandSession) -> tuple[float, int]:
        """Collect CPU usage percentage and core count via SSH.

        Primary: vmstat sums us+sy+wa+st columns (total non-idle CPU).
        Fallback: /proc/stat 1-second delta when vmstat is unavailable.
        """
        cpu_usage = 0.0
        vmstat_ok = False
        try:
            stdout, _, exit_code = await connector.execute_command(
                "vmstat 1 2 | tail -1 | awk '{print $13+$14+$16+$17}'"
            )
            if exit_code == 0 and stdout.strip():
                cpu_usage = float(stdout.strip())
                vmstat_ok = True
        except Exception:  # nosec B110 — intentional fallback
            pass

        if not vmstat_ok:
            audit.info("node.metrics.cpu.fallback_proc_stat")
            cpu_usage = await NodeMetricsService._cpu_from_proc_stat(connector)

        cpu_usage = max(0.0, min(100.0, cpu_usage))

        cores_stdout, _, _ = await connector.execute_command("nproc")
        cores = int(cores_stdout.strip()) if cores_stdout.strip() else 1
        return cpu_usage, cores

    @staticmethod
    async def _cpu_from_proc_stat(connector: RemoteCommandSession) -> float:
        """Derive CPU usage from a 1-second /proc/stat delta."""
        try:
            s1, _, ec1 = await connector.execute_command("head -1 /proc/stat")
            if ec1 != 0 or not s1.strip():
                return 0.0
            await connector.execute_command("sleep 1")
            s2, _, ec2 = await connector.execute_command("head -1 /proc/stat")
            if ec2 != 0 or not s2.strip():
                return 0.0

            vals1 = [int(v) for v in s1.strip().split()[1:]]
            vals2 = [int(v) for v in s2.strip().split()[1:]]

            idle1, idle2 = vals1[3], vals2[3]
            total1, total2 = sum(vals1), sum(vals2)

            d_idle = idle2 - idle1
            d_total = total2 - total1
            if d_total == 0:
                return 0.0
            return (d_total - d_idle) / d_total * 100
        except Exception:  # nosec B110 — intentional fallback if /proc/stat unavailable
            return 0.0

    @staticmethod
    async def _collect_load_average(
        connector: RemoteCommandSession,
    ) -> LoadAverageDTO:
        """Collect 1/5/15 min load averages from /proc/loadavg."""
        stdout, _, exit_code = await connector.execute_command(
            "cat /proc/loadavg | awk '{print $1, $2, $3}'"
        )
        if exit_code == 0:
            parts = stdout.strip().split()
            if len(parts) >= 3:
                return LoadAverageDTO(
                    one_min=float(parts[0]),
                    five_min=float(parts[1]),
                    fifteen_min=float(parts[2]),
                )
        return LoadAverageDTO(one_min=0.0, five_min=0.0, fifteen_min=0.0)

    @staticmethod
    async def _collect_usage(
        connector: RemoteCommandSession,
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
