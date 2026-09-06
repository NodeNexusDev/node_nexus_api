"""Bulk node operation service."""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Literal

import structlog

from app.application.dto.bulk_node_operation import (
    BulkNodeCheckResultDTO,
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)
from app.application.ports.node_bulk_operator import NodeBulkOperator

if TYPE_CHECKING:
    from app.application.ports.audit_sink import AuditEventSink
    from app.application.ports.credential_cipher import CredentialCipher
    from app.application.ports.node_management import NodeManagementReader
    from app.application.ports.node_reader import NodeConnectionReader, NodeStatusWriter
    from app.application.ports.node_status_history import NodeStatusHistoryWriter
    from app.application.ports.remote_command import RemoteConnectorFactory

audit = structlog.get_logger("audit")

_DEFAULT_CHECK_CONCURRENCY = 50


class NodeBulkOperationService:
    """Execute bulk operations on nodes."""

    def __init__(
        self,
        operator: NodeBulkOperator,
        audit_service: AuditEventSink | None = None,
        node_reader: NodeConnectionReader | None = None,
        status_writer: NodeStatusWriter | None = None,
        credential_cipher: CredentialCipher | None = None,
        connector_factory: RemoteConnectorFactory | None = None,
        status_history_writer: NodeStatusHistoryWriter | None = None,
        node_view_reader: NodeManagementReader | None = None,
    ) -> None:
        self._operator = operator
        self._audit = audit_service
        self._node_reader = node_reader
        self._status_writer = status_writer
        self._credential_cipher = credential_cipher
        self._connector_factory = connector_factory
        self._status_history_writer = status_history_writer
        self._node_view_reader = node_view_reader
        self._check_semaphore = asyncio.Semaphore(_DEFAULT_CHECK_CONCURRENCY)

    async def bulk_delete(self, data: BulkNodeDeleteDTO) -> BulkNodeOperationResultDTO:
        """Delete multiple nodes."""
        result = await self._operator.bulk_delete(data)
        if self._audit:
            await self._audit.log(
                action="bulk_nodes.delete",
                details={
                    "affected": result.affected,
                    "requested": len(data.node_ids),
                },
            )
        audit.info(
            "node.bulk.delete",
            affected=result.affected,
            requested=len(data.node_ids),
        )
        return result

    async def bulk_add_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Add tags to multiple nodes."""
        result = await self._operator.bulk_add_tags(data)
        if self._audit:
            await self._audit.log(
                action="bulk_nodes.add_tags",
                details={
                    "affected": result.affected,
                    "tags": list(data.tags),
                },
            )
        audit.info(
            "node.bulk.add_tags",
            affected=result.affected,
            tags=data.tags,
        )
        return result

    async def bulk_remove_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Remove tags from multiple nodes."""
        result = await self._operator.bulk_remove_tags(data)
        if self._audit:
            await self._audit.log(
                action="bulk_nodes.remove_tags",
                details={
                    "affected": result.affected,
                    "tags": list(data.tags),
                },
            )
        audit.info(
            "node.bulk.remove_tags",
            affected=result.affected,
            tags=data.tags,
        )
        return result

    async def bulk_check(
        self,
        node_ids: tuple[str, ...],
        mode: Literal["db", "ssh"] = "ssh",
    ) -> BulkNodeCheckResultDTO:
        """Check which nodes exist by IDs or via SSH.

        Modes:
        - db: check existence in DB (legacy)
        - ssh: SSH connectivity check with status update (echo ok) — default
        """
        if mode == "db":
            result = await self._operator.bulk_check(node_ids)
            if self._audit:
                await self._audit.log(
                    action="bulk_nodes.check",
                    details={
                        "total": result.total,
                        "succeeded": result.succeeded,
                        "failed": result.failed,
                        "mode": mode,
                    },
                )
            audit.info(
                "node.bulk.check",
                total=result.total,
                succeeded=result.succeeded,
                failed=result.failed,
                mode=mode,
            )
            return result

        # ssh mode
        if (
            self._node_reader is None
            or self._connector_factory is None
            or self._credential_cipher is None
        ):
            # Fallback to db if ssh deps not configured (e.g., in tests with mocks)
            audit.warning("node.bulk.check.ssh_fallback_to_db", reason="missing_deps")
            result = await self._operator.bulk_check(node_ids)
            return result

        if (
            self._node_reader is None
            or self._credential_cipher is None
            or self._connector_factory is None
        ):
            raise RuntimeError("SSH dependencies are not configured")
        node_reader = self._node_reader
        credential_cipher = self._credential_cipher
        connector_factory = self._connector_factory

        # Lazy import to avoid circular deps
        from app.application.dto.node_status_history import NodeStatusChangeDTO
        from app.application.services.ssh_executor import build_ssh_connector
        from app.core.exceptions import ConnectionFailedError, CredentialDecryptionError
        from app.core.types import NodeStatus

        async def _check_one(
            node_id_str: str,
        ) -> tuple[str, bool, str | None, NodeStatus | None]:
            try:
                node_uuid = uuid.UUID(node_id_str)
            except ValueError:
                return (node_id_str, False, "Invalid node id", None)

            node = await node_reader.get_connection(node_uuid)
            if node is None:
                return (node_id_str, False, "Node not found", None)

            connector = build_ssh_connector(node, credential_cipher, connector_factory)

            try:
                async with connector:
                    await connector.execute_command("echo ok")
                new_status: NodeStatus = "active"
                success = True
                error = None
                audit.info("node.bulk.check.ssh_ok", node_id=node_id_str)
            except CredentialDecryptionError as exc:
                new_status = "error"
                success = False
                error = str(exc)
                audit.error(
                    "node.bulk.check.credential_failed",
                    node_id=node_id_str,
                    error=str(exc),
                )
            except ConnectionFailedError as exc:
                new_status = "unreachable"
                success = False
                error = str(exc)
                audit.warning(
                    "node.bulk.check.ssh_failed",
                    node_id=node_id_str,
                    error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                new_status = "unreachable"
                success = False
                error = str(exc)
                audit.error(
                    "node.bulk.check.ssh_unexpected",
                    node_id=node_id_str,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

            # Fetch old status for history
            old_status: NodeStatus | None = None
            if self._node_view_reader is not None:
                try:
                    view = await self._node_view_reader.get_node(node_uuid)
                    old_status = view.status if view else None
                except Exception:  # noqa: BLE001
                    old_status = None

            # Update status and history — honest: DB failure => failed
            status_ok = True
            if self._status_writer is not None:
                try:
                    updated = await self._status_writer.update_node_status(
                        node_uuid, new_status
                    )
                    if updated is None:
                        # Node vanished between read and write
                        status_ok = False
                        success = False
                        error = "Node not found on status update"
                        audit.warning(
                            "node.bulk.check.status_not_found",
                            node_id=node_id_str,
                        )
                except Exception as exc:  # noqa: BLE001
                    status_ok = False
                    success = False
                    error = f"Status update failed: {exc}"
                    audit.warning(
                        "node.bulk.check.status_update_failed",
                        node_id=node_id_str,
                        error=str(exc),
                    )
            # Skip history if no change or status write failed (best-effort)
            should_write_history = (
                self._status_history_writer is not None
                and status_ok
                and old_status != new_status
            )
            if should_write_history:
                # should_write_history guarantees writer is not None
                if self._status_history_writer is None:
                    raise RuntimeError("Status history writer is not configured")
                try:
                    await self._status_history_writer.save(
                        NodeStatusChangeDTO(
                            node_id=node_uuid,
                            old_status=old_status,
                            new_status=new_status,
                            source="connectivity_check",
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    audit.warning(
                        "node.bulk.check.history_failed",
                        node_id=node_id_str,
                        error=str(exc),
                    )
            elif (
                self._status_history_writer is not None
                and old_status == new_status
                and status_ok
            ):
                audit.info(
                    "node.bulk.check.history_skipped_noop",
                    node_id=node_id_str,
                    status=new_status,
                )

            # If status update failed, override success
            if not status_ok:
                success = False

            return (node_id_str, success, error, new_status)

        async def _check_one_sem(  # noqa: ANN202
            node_id_str: str,
        ) -> tuple[str, bool, str | None, NodeStatus | None]:
            async with self._check_semaphore:
                return await _check_one(node_id_str)

        results = await asyncio.gather(*(_check_one_sem(nid) for nid in node_ids))

        succeeded_ids: list[uuid.UUID] = []
        succeeded = 0
        failed = 0
        from app.application.dto.bulk_node_operation import BulkNodeCheckDetailDTO

        details: list[BulkNodeCheckDetailDTO] = []
        for nid_str, ok, _err, _st in results:
            details.append(
                BulkNodeCheckDetailDTO(
                    node_id=nid_str, success=ok, error=_err, new_status=_st
                )
            )
            if ok:
                succeeded += 1
                try:
                    succeeded_ids.append(uuid.UUID(nid_str))
                except ValueError:
                    pass
            else:
                failed += 1

        total = len(node_ids)
        # For API handler, succeeded/failed already counted, but also
        # include node_ids for compatibility
        result = BulkNodeCheckResultDTO(
            total=total,
            succeeded=succeeded,
            failed=failed,
            node_ids=tuple(succeeded_ids),
            details=tuple(details),
        )

        if self._audit:
            await self._audit.log(
                action="bulk_nodes.check",
                details={
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "mode": mode,
                },
            )
        audit.info(
            "node.bulk.check",
            total=total,
            succeeded=succeeded,
            failed=failed,
            mode=mode,
        )
        return result
