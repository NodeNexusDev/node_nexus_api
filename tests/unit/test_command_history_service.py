"""Unit tests for ExecutionHistoryService.get_node_history."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.dto.command_history import (
    CommandHistoryDTO,
    CommandHistoryPageDTO,
    CommandHistoryQueryDTO,
)
from app.application.services.execution_history_service import ExecutionHistoryService


@pytest.fixture
def reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(reader: AsyncMock) -> ExecutionHistoryService:
    return ExecutionHistoryService(reader)


async def test_get_node_history_builds_query(
    service: ExecutionHistoryService, reader: AsyncMock
) -> None:
    node_id = uuid.uuid4()
    now = datetime.now(UTC)
    dto = CommandHistoryDTO(
        id=uuid.uuid4(),
        node_id=node_id,
        command_id=None,
        batch_id=None,
        command_fingerprint="abc",
        exit_code=0,
        stdout="ok",
        stderr="",
        stdout_bytes=2,
        stderr_bytes=0,
        truncated=False,
        started_at=now,
        finished_at=now,
        created_at=now,
    )
    reader.list_by_node.return_value = CommandHistoryPageDTO(items=(dto,), total=1)

    result = await service.get_node_history(node_id, page=2, size=10)

    assert result.total == 1
    assert result.items == (dto,)
    query = reader.list_by_node.await_args.args[0]
    assert isinstance(query, CommandHistoryQueryDTO)
    assert query.node_id == node_id
    assert query.offset == 10
    assert query.limit == 10
