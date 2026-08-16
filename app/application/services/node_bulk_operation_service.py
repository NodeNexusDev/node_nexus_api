"""Bulk node operation service."""

from __future__ import annotations

from app.application.dto.bulk_node_operation import (
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)
from app.application.ports.node_bulk_operator import NodeBulkOperator


class NodeBulkOperationService:
    """Execute bulk operations on nodes."""

    def __init__(self, operator: NodeBulkOperator) -> None:
        self._operator = operator

    async def bulk_delete(self, data: BulkNodeDeleteDTO) -> BulkNodeOperationResultDTO:
        """Delete multiple nodes."""
        return await self._operator.bulk_delete(data)

    async def bulk_add_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Add tags to multiple nodes."""
        return await self._operator.bulk_add_tags(data)

    async def bulk_remove_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO:
        """Remove tags from multiple nodes."""
        return await self._operator.bulk_remove_tags(data)
