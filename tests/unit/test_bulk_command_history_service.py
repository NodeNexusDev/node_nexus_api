"""Unit tests for ExecutionHistoryService.get_batch_history."""

import uuid
from datetime import UTC, datetime
from typing import override

import pytest

from app.application.dto.command_history import (
    BulkCommandHistoryQueryDTO,
    CommandHistoryDTO,
    CommandHistoryPageDTO,
    CommandHistoryQueryDTO,
)
from app.application.ports.command_history import CommandHistoryReader
from app.application.services.execution_history_service import ExecutionHistoryService


class FakeReader(CommandHistoryReader):
    def __init__(self, items: list[CommandHistoryDTO]) -> None:
        self._items = items
        self.last_query: BulkCommandHistoryQueryDTO | None = None

    @override
    async def list_by_node(
        self, query: CommandHistoryQueryDTO
    ) -> CommandHistoryPageDTO:
        raise NotImplementedError

    @override
    async def list_by_batch(
        self, query: BulkCommandHistoryQueryDTO
    ) -> CommandHistoryPageDTO:
        self.last_query = query
        matched = [i for i in self._items if i.batch_id == query.batch_id]
        return CommandHistoryPageDTO(
            items=tuple(matched[query.offset : query.offset + query.limit]),
            total=len(matched),
        )

    @override
    async def get_by_id(self, execution_id: uuid.UUID) -> CommandHistoryDTO | None:
        raise NotImplementedError


def _make_dto(batch_id: uuid.UUID) -> CommandHistoryDTO:
    now = datetime.now(UTC)
    return CommandHistoryDTO(
        id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        command_id=None,
        batch_id=batch_id,
        command_fingerprint="fp",
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


@pytest.mark.asyncio
async def test_get_batch_history_filters_by_batch_id() -> None:
    batch_id = uuid.uuid4()
    other = uuid.uuid4()
    items = [_make_dto(batch_id), _make_dto(other)]
    reader = FakeReader(items)
    service = ExecutionHistoryService(reader)

    result = await service.get_batch_history(batch_id, page=1, size=10)

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].batch_id == batch_id


@pytest.mark.asyncio
async def test_get_batch_history_pagination_offset() -> None:
    batch_id = uuid.uuid4()
    items = [_make_dto(batch_id) for _ in range(5)]
    reader = FakeReader(items)
    service = ExecutionHistoryService(reader)

    result = await service.get_batch_history(batch_id, page=2, size=2)

    assert result.total == 5
    assert len(result.items) == 2
    assert reader.last_query is not None
    assert reader.last_query.offset == 2
    assert reader.last_query.limit == 2
