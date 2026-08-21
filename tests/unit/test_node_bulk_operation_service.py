"""Unit tests for NodeBulkOperationService audit branches."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.dto.bulk_node_operation import (
    BulkNodeCheckResultDTO,
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)

NODE_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class TestBulkDeleteAudit:
    @pytest.mark.asyncio
    async def test_bulk_delete_with_audit(self) -> None:
        operator = AsyncMock()
        audit = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=audit)
        operator.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_delete(BulkNodeDeleteDTO(node_ids=(NODE_ID,)))
        assert result.affected == 1
        audit.log.assert_awaited_once_with(
            action="bulk_nodes.delete",
            details={"affected": 1, "requested": 1},
        )

    @pytest.mark.asyncio
    async def test_bulk_delete_without_audit(self) -> None:
        operator = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=None)
        operator.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_delete(BulkNodeDeleteDTO(node_ids=(NODE_ID,)))
        assert result.affected == 1


class TestBulkAddTagsAudit:
    @pytest.mark.asyncio
    async def test_bulk_add_tags_with_audit(self) -> None:
        operator = AsyncMock()
        audit = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=audit)
        operator.bulk_add_tags.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_add_tags(
            BulkNodeTagOperationDTO(node_ids=(NODE_ID,), tags=("prod",))
        )
        assert result.affected == 1
        audit.log.assert_awaited_once_with(
            action="bulk_nodes.add_tags",
            details={"affected": 1, "tags": ["prod"]},
        )

    @pytest.mark.asyncio
    async def test_bulk_add_tags_without_audit(self) -> None:
        operator = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=None)
        operator.bulk_add_tags.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_add_tags(
            BulkNodeTagOperationDTO(node_ids=(NODE_ID,), tags=("prod",))
        )
        assert result.affected == 1


class TestBulkRemoveTagsAudit:
    @pytest.mark.asyncio
    async def test_bulk_remove_tags_with_audit(self) -> None:
        operator = AsyncMock()
        audit = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=audit)
        operator.bulk_remove_tags.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_remove_tags(
            BulkNodeTagOperationDTO(node_ids=(NODE_ID,), tags=("prod",))
        )
        assert result.affected == 1
        audit.log.assert_awaited_once_with(
            action="bulk_nodes.remove_tags",
            details={"affected": 1, "tags": ["prod"]},
        )

    @pytest.mark.asyncio
    async def test_bulk_remove_tags_without_audit(self) -> None:
        operator = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=None)
        operator.bulk_remove_tags.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_remove_tags(
            BulkNodeTagOperationDTO(node_ids=(NODE_ID,), tags=("prod",))
        )
        assert result.affected == 1


class TestBulkCheckAudit:
    @pytest.mark.asyncio
    async def test_bulk_check_with_audit(self) -> None:
        operator = AsyncMock()
        audit = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=audit)
        operator.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=1, succeeded=1, failed=0, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_check(node_ids=(str(NODE_ID),))
        assert result.succeeded == 1
        audit.log.assert_awaited_once_with(
            action="bulk_nodes.check",
            details={"total": 1, "succeeded": 1, "failed": 0},
        )

    @pytest.mark.asyncio
    async def test_bulk_check_without_audit(self) -> None:
        operator = AsyncMock()
        svc = NodeBulkOperationService(operator=operator, audit_service=None)
        operator.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=1, succeeded=1, failed=0, node_ids=(NODE_ID,)
        )
        result = await svc.bulk_check(node_ids=(str(NODE_ID),))
        assert result.succeeded == 1
