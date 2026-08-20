"""Bulk node operation service."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

audit = structlog.get_logger("audit")


class NodeBulkOperationService:
    """Execute bulk operations on nodes."""

    def __init__(
        self,
        operator: NodeBulkOperator,
        audit_service: AuditEventSink | None = None,
    ) -> None:
        self._operator = operator
        self._audit = audit_service

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

    async def bulk_check(self, node_ids: tuple[str, ...]) -> BulkNodeCheckResultDTO:
        """Check which nodes exist by IDs."""
        result = await self._operator.bulk_check(node_ids)
        if self._audit:
            await self._audit.log(
                action="bulk_nodes.check",
                details={
                    "total": result.total,
                    "succeeded": result.succeeded,
                    "failed": result.failed,
                },
            )
        audit.info(
            "node.bulk.check",
            total=result.total,
            succeeded=result.succeeded,
            failed=result.failed,
        )
        return result
