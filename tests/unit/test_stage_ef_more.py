"""Additional tests for low-coverage DAOs and adapters — bulk_operator,
command_execution, execution_stats gateway."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.persistence.dao.command_execution import (
    CommandExecutionRepository,
)
from app.adapters.persistence.node_bulk_operator import SqlAlchemyNodeBulkOperator
from app.models.command_execution import CommandExecutionModel

# ─── CommandExecutionRepository ───


class TestCommandExecutionRepository:
    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = AsyncMock()
        session.add = MagicMock()
        repo = CommandExecutionRepository(session)
        data = {
            "node_id": uuid.uuid4(),
            "command_id": uuid.uuid4(),
            "command_fingerprint": "abc",
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
            "started_at": datetime.now(UTC),
            "finished_at": datetime.now(UTC),
        }
        result = await repo.create(data)
        assert isinstance(result, CommandExecutionModel)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self) -> None:
        session = AsyncMock()
        repo = CommandExecutionRepository(session)
        model = CommandExecutionModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            command_id=uuid.uuid4(),
            command_fingerprint="abc",
            stdout="",
            stderr="",
            exit_code=0,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute.return_value = mock_result

        result = await repo.get_by_id(model.id)
        assert result is model

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self) -> None:
        session = AsyncMock()
        repo = CommandExecutionRepository(session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_node(self) -> None:
        session = AsyncMock()
        repo = CommandExecutionRepository(session)
        model = CommandExecutionModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            command_id=uuid.uuid4(),
            command_fingerprint="abc",
            stdout="",
            stderr="",
            exit_code=0,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        session.execute.return_value = mock_result

        assert model.node_id is not None
        result = await repo.list_by_node(model.node_id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_by_batch(self) -> None:
        session = AsyncMock()
        repo = CommandExecutionRepository(session)
        model = CommandExecutionModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            command_id=uuid.uuid4(),
            batch_id=uuid.uuid4(),
            command_fingerprint="abc",
            stdout="",
            stderr="",
            exit_code=0,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        session.execute.return_value = mock_result

        assert model.batch_id is not None
        result = await repo.list_by_batch(model.batch_id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_by_node(self) -> None:
        session = AsyncMock()
        repo = CommandExecutionRepository(session)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        session.execute.return_value = mock_result

        result = await repo.count_by_node(uuid.uuid4())
        assert result == 5

    @pytest.mark.asyncio
    async def test_count_by_batch(self) -> None:
        session = AsyncMock()
        repo = CommandExecutionRepository(session)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        session.execute.return_value = mock_result

        result = await repo.count_by_batch(uuid.uuid4())
        assert result == 3


# ─── NodeBulkOperator ───


class TestNodeBulkOperator:
    @pytest.mark.asyncio
    async def test_bulk_delete(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeBulkOperator(sm)

        from app.application.dto.bulk_node_operation import BulkNodeDeleteDTO

        node_id1, node_id2 = uuid.uuid4(), uuid.uuid4()
        mock_select = MagicMock()
        mock_select.all.return_value = [(node_id1,), (node_id2,)]
        mock_delete = MagicMock()
        session.execute = AsyncMock(side_effect=[mock_select, mock_delete])

        result = await gw.bulk_delete(BulkNodeDeleteDTO(node_ids=(node_id1, node_id2)))
        assert result.affected == 2
        assert set(result.node_ids) == {node_id1, node_id2}

    @pytest.mark.asyncio
    async def test_bulk_add_tags(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeBulkOperator(sm)

        from app.application.dto.bulk_node_operation import BulkNodeTagOperationDTO

        node_id = uuid.uuid4()
        node = MagicMock()
        node.tags = ("existing",)
        node.id = node_id

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [node]
        session.execute = AsyncMock(return_value=mock_select_result)

        result = await gw.bulk_add_tags(
            BulkNodeTagOperationDTO(node_ids=(node_id,), tags=("new",))
        )
        assert result.affected == 1

    @pytest.mark.asyncio
    async def test_bulk_add_tags_already_has(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeBulkOperator(sm)

        from app.application.dto.bulk_node_operation import BulkNodeTagOperationDTO

        node_id = uuid.uuid4()
        node = MagicMock()
        node.tags = ("tag1",)
        node.id = node_id

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [node]
        session.execute = AsyncMock(return_value=mock_select_result)

        result = await gw.bulk_add_tags(
            BulkNodeTagOperationDTO(node_ids=(node_id,), tags=("tag1",))
        )
        assert result.affected == 0

    @pytest.mark.asyncio
    async def test_bulk_remove_tags(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeBulkOperator(sm)

        from app.application.dto.bulk_node_operation import BulkNodeTagOperationDTO

        node_id = uuid.uuid4()
        node = MagicMock()
        node.tags = ("keep", "remove")
        node.id = node_id

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [node]
        session.execute = AsyncMock(return_value=mock_select_result)

        result = await gw.bulk_remove_tags(
            BulkNodeTagOperationDTO(node_ids=(node_id,), tags=("remove",))
        )
        assert result.affected == 1

    @pytest.mark.asyncio
    async def test_bulk_remove_tags_no_change(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeBulkOperator(sm)

        from app.application.dto.bulk_node_operation import BulkNodeTagOperationDTO

        node_id = uuid.uuid4()
        node = MagicMock()
        node.tags = ("keep",)
        node.id = node_id

        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [node]
        session.execute = AsyncMock(return_value=mock_select_result)

        result = await gw.bulk_remove_tags(
            BulkNodeTagOperationDTO(node_ids=(node_id,), tags=("other",))
        )
        assert result.affected == 0

    @pytest.mark.asyncio
    async def test_bulk_delete_nonexistent(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeBulkOperator(sm)

        from app.application.dto.bulk_node_operation import BulkNodeDeleteDTO

        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)

        result = await gw.bulk_delete(BulkNodeDeleteDTO(node_ids=(uuid.uuid4(),)))
        assert result.affected == 0
