"""Unit tests for Stage D — Node status history and bulk operations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.dto.bulk_node_operation import (
    BulkNodeDeleteDTO,
    BulkNodeOperationResultDTO,
    BulkNodeTagOperationDTO,
)
from app.application.dto.execution_lifecycle import (
    CancelExecutionDTO,
    RetryCommandDTO,
    RetryScriptDTO,
)
from app.application.dto.node_status_history import (
    NodeStatusChangeDTO,
    NodeStatusHistoryPageDTO,
    NodeStatusHistoryQueryDTO,
    NodeStatusHistoryRecordDTO,
)
from app.application.ports.command_history import CommandHistoryReader
from app.application.ports.execution_lifecycle import ExecutionLifecycleManager
from app.application.ports.node_bulk_operator import NodeBulkOperator
from app.application.ports.node_status_history import (
    NodeStatusHistoryReader,
    NodeStatusHistoryWriter,
)
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)


@pytest.fixture()
def writer() -> AsyncMock:
    return AsyncMock(spec=NodeStatusHistoryWriter)


@pytest.fixture()
def reader() -> AsyncMock:
    return AsyncMock(spec=NodeStatusHistoryReader)


@pytest.fixture()
def service(reader: AsyncMock, writer: AsyncMock) -> NodeStatusHistoryService:
    return NodeStatusHistoryService(reader=reader, writer=writer)


# --- DTO tests ---


def test_status_change_dto_is_frozen() -> None:
    dto = NodeStatusChangeDTO(
        node_id=uuid.uuid4(),
        old_status="active",
        new_status="unreachable",
        source="connectivity_check",
    )
    with pytest.raises(AttributeError):
        dto.new_status = "active"  # type: ignore[misc]


def test_status_history_record_dto_fields() -> None:
    now = datetime.now(UTC)
    record = NodeStatusHistoryRecordDTO(
        id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        old_status="active",
        new_status="unreachable",
        source="connectivity_check",
        changed_at=now,
    )
    assert record.new_status == "unreachable"
    assert record.changed_at == now


def test_status_history_query_dto_defaults() -> None:
    query = NodeStatusHistoryQueryDTO(node_id=uuid.uuid4())
    assert query.offset == 0
    assert query.limit == 20


def test_status_history_page_dto() -> None:
    page = NodeStatusHistoryPageDTO(items=(), total=0)
    assert page.items == ()
    assert page.total == 0


# --- Service tests ---


@pytest.mark.asyncio()
async def test_record_status_change(
    service: NodeStatusHistoryService, writer: AsyncMock
) -> None:
    data = NodeStatusChangeDTO(
        node_id=uuid.uuid4(),
        old_status="active",
        new_status="unreachable",
        source="connectivity_check",
    )
    await service.record_status_change(data)
    writer.save.assert_awaited_once_with(data)


@pytest.mark.asyncio()
async def test_get_history(
    service: NodeStatusHistoryService, reader: AsyncMock
) -> None:
    query = NodeStatusHistoryQueryDTO(node_id=uuid.uuid4(), offset=0, limit=10)
    expected = NodeStatusHistoryPageDTO(items=(), total=0)
    reader.list_by_node.return_value = expected
    result = await service.get_history(query)
    reader.list_by_node.assert_awaited_once_with(query)
    assert result == expected


# --- Bulk node operations ---


@pytest.fixture()
def bulk_operator() -> AsyncMock:
    return AsyncMock(spec=NodeBulkOperator)


@pytest.fixture()
def bulk_service(bulk_operator: AsyncMock) -> NodeBulkOperationService:
    return NodeBulkOperationService(operator=bulk_operator)


def test_bulk_delete_dto_is_frozen() -> None:
    dto = BulkNodeDeleteDTO(node_ids=(uuid.uuid4(),))
    with pytest.raises(AttributeError):
        dto.node_ids = ()  # type: ignore[misc]


def test_bulk_tag_operation_dto_is_frozen() -> None:
    dto = BulkNodeTagOperationDTO(node_ids=(uuid.uuid4(),), tags=("web",))
    with pytest.raises(AttributeError):
        dto.tags = ()  # type: ignore[misc]


def test_bulk_operation_result_dto() -> None:
    result = BulkNodeOperationResultDTO(
        affected=2, node_ids=(uuid.uuid4(), uuid.uuid4())
    )
    assert result.affected == 2
    assert len(result.node_ids) == 2


@pytest.mark.asyncio()
async def test_bulk_delete(
    bulk_service: NodeBulkOperationService, bulk_operator: AsyncMock
) -> None:
    node_id = uuid.uuid4()
    expected = BulkNodeOperationResultDTO(affected=1, node_ids=(node_id,))
    bulk_operator.bulk_delete.return_value = expected
    result = await bulk_service.bulk_delete(BulkNodeDeleteDTO(node_ids=(node_id,)))
    bulk_operator.bulk_delete.assert_awaited_once()
    assert result == expected


@pytest.mark.asyncio()
async def test_bulk_add_tags(
    bulk_service: NodeBulkOperationService, bulk_operator: AsyncMock
) -> None:
    node_id = uuid.uuid4()
    expected = BulkNodeOperationResultDTO(affected=1, node_ids=(node_id,))
    bulk_operator.bulk_add_tags.return_value = expected
    result = await bulk_service.bulk_add_tags(
        BulkNodeTagOperationDTO(node_ids=(node_id,), tags=("web",))
    )
    bulk_operator.bulk_add_tags.assert_awaited_once()
    assert result == expected


@pytest.mark.asyncio()
async def test_bulk_remove_tags(
    bulk_service: NodeBulkOperationService, bulk_operator: AsyncMock
) -> None:
    node_id = uuid.uuid4()
    expected = BulkNodeOperationResultDTO(affected=1, node_ids=(node_id,))
    bulk_operator.bulk_remove_tags.return_value = expected
    result = await bulk_service.bulk_remove_tags(
        BulkNodeTagOperationDTO(node_ids=(node_id,), tags=("web",))
    )
    bulk_operator.bulk_remove_tags.assert_awaited_once()
    assert result == expected


# --- Execution lifecycle ---


@pytest.fixture()
def lifecycle_manager() -> AsyncMock:
    return AsyncMock(spec=ExecutionLifecycleManager)


@pytest.fixture()
def command_history_reader() -> AsyncMock:
    return AsyncMock(spec=CommandHistoryReader)


@pytest.fixture()
def lifecycle_service(
    lifecycle_manager: AsyncMock, command_history_reader: AsyncMock
) -> ExecutionLifecycleService:
    return ExecutionLifecycleService(
        manager=lifecycle_manager,
        command_history_reader=command_history_reader,
    )


def test_retry_command_dto_is_frozen() -> None:
    dto = RetryCommandDTO(execution_id=uuid.uuid4(), node_id=uuid.uuid4())
    with pytest.raises(AttributeError):
        dto.execution_id = uuid.uuid4()  # type: ignore[misc]


def test_retry_script_dto_is_frozen() -> None:
    dto = RetryScriptDTO(execution_id=uuid.uuid4())
    with pytest.raises(AttributeError):
        dto.execution_id = uuid.uuid4()  # type: ignore[misc]


def test_cancel_execution_dto_is_frozen() -> None:
    dto = CancelExecutionDTO(execution_id=uuid.uuid4())
    with pytest.raises(AttributeError):
        dto.execution_id = uuid.uuid4()  # type: ignore[misc]


@pytest.mark.asyncio()
async def test_retry_command(
    lifecycle_service: ExecutionLifecycleService,
    lifecycle_manager: AsyncMock,
    command_history_reader: AsyncMock,
) -> None:
    exec_id = uuid.uuid4()
    node_id = uuid.uuid4()
    mock_execution = MagicMock()
    mock_execution.id = exec_id
    mock_execution.node_id = node_id
    mock_execution.command_fingerprint = "abc123"
    command_history_reader.get_by_id.return_value = mock_execution
    result = await lifecycle_service.retry_command(
        RetryCommandDTO(execution_id=exec_id, node_id=node_id)
    )
    command_history_reader.get_by_id.assert_awaited_once_with(exec_id)
    assert result.status == "retry_scheduled"
    assert result.execution_id == str(exec_id)


@pytest.mark.asyncio()
async def test_retry_command_not_found(
    lifecycle_service: ExecutionLifecycleService,
    lifecycle_manager: AsyncMock,
    command_history_reader: AsyncMock,
) -> None:
    command_history_reader.get_by_id.return_value = None
    from app.core.exceptions import ExecutionNotFoundError

    with pytest.raises(ExecutionNotFoundError):
        await lifecycle_service.retry_command(
            RetryCommandDTO(execution_id=uuid.uuid4(), node_id=uuid.uuid4())
        )


@pytest.mark.asyncio()
async def test_retry_script(
    lifecycle_service: ExecutionLifecycleService, lifecycle_manager: AsyncMock
) -> None:
    exec_id = uuid.uuid4()
    result = await lifecycle_service.retry_script(RetryScriptDTO(execution_id=exec_id))
    assert result.status == "retry_scheduled"
    assert result.execution_id == str(exec_id)


@pytest.mark.asyncio()
async def test_cancel_execution(
    lifecycle_service: ExecutionLifecycleService, lifecycle_manager: AsyncMock
) -> None:
    exec_id = uuid.uuid4()
    lifecycle_manager.cancel_execution.return_value = True
    result = await lifecycle_service.cancel_execution(
        CancelExecutionDTO(execution_id=exec_id)
    )
    lifecycle_manager.cancel_execution.assert_awaited_once()
    assert result is True


@pytest.mark.asyncio()
async def test_cancel_execution_not_found(
    lifecycle_service: ExecutionLifecycleService, lifecycle_manager: AsyncMock
) -> None:
    lifecycle_manager.cancel_execution.return_value = False
    from app.core.exceptions import ExecutionNotFoundError

    with pytest.raises(ExecutionNotFoundError):
        await lifecycle_service.cancel_execution(
            CancelExecutionDTO(execution_id=uuid.uuid4())
        )
