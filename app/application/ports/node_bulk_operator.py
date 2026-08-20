"""Bulk node operation port."""

from __future__ import annotations

from typing import Protocol

from app.application.dto.bulk_node_operation import (
    BulkNodeCheckResultDTO,
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)


class NodeBulkOperator(Protocol):
    async def bulk_delete(
        self, data: BulkNodeDeleteDTO
    ) -> BulkNodeOperationResultDTO: ...

    async def bulk_add_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO: ...

    async def bulk_remove_tags(
        self, data: BulkNodeTagOperationDTO
    ) -> BulkNodeOperationResultDTO: ...

    async def bulk_check(
        self, node_ids: tuple[str, ...]
    ) -> BulkNodeCheckResultDTO: ...
