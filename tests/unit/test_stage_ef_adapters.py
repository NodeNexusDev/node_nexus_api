"""Tests for Stage E/F adapters — favorite, note, tag_manager, execution_stats,
global_search, audit_export, dashboard_metrics, node_status_history DAOs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.audit_export import SqlAlchemyAuditExporter
from app.adapters.persistence.dao.dashboard_metrics import (
    DashboardMetricsRepository,
)
from app.adapters.persistence.dao.execution_stats import ExecutionStatsRepository
from app.adapters.persistence.dao.node_status_history import (
    NodeStatusHistoryRepository,
)
from app.adapters.persistence.execution_lifecycle import (
    SqlAlchemyExecutionLifecycleGateway,
)
from app.adapters.persistence.execution_stats import SqlAlchemyExecutionStatsGateway
from app.adapters.persistence.favorite import SqlAlchemyFavoriteGateway
from app.adapters.persistence.global_search import SqlAlchemyGlobalSearchGateway
from app.adapters.persistence.node_status_history import (
    SqlAlchemyNodeStatusHistoryGateway,
)
from app.adapters.persistence.note import SqlAlchemyNoteGateway
from app.adapters.persistence.tag_manager import SqlAlchemyTagManager
from app.application.dto.execution_stats import (
    CommandStatsQueryDTO,
    ExecutionStatsDTO,
    ScriptStatsQueryDTO,
)
from app.application.dto.export import AuditExportQueryDTO, AuditExportRowDTO
from app.application.dto.favorite import FavoriteCreateDTO, FavoriteDTO
from app.application.dto.global_search import (
    GlobalSearchQueryDTO,
    GlobalSearchResultDTO,
)
from app.application.dto.node_status_history import (
    NodeStatusChangeDTO,
    NodeStatusHistoryPageDTO,
    NodeStatusHistoryQueryDTO,
)
from app.application.dto.note import NoteCreateDTO, NoteDTO, NoteUpdateDTO
from app.models.favorite import FavoriteModel
from app.models.node_status_history import NodeStatusHistoryModel
from app.models.note import NoteModel

# ─── Favorite adapter ───


class TestFavoriteGateway:
    @pytest.mark.asyncio
    async def test_add_favorite(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)
        data = FavoriteCreateDTO(
            target_type="command",
            target_id=uuid.uuid4(),
            note="important",
        )
        result = await gw.add_favorite(data)
        assert isinstance(result, FavoriteDTO)
        assert result.target_type == "command"
        assert result.note == "important"
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_favorite_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)
        model = FavoriteModel(
            id=uuid.uuid4(),
            target_type="script",
            target_id=uuid.uuid4(),
            name=None,
            note=None,
            created_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute.return_value = mock_result

        result = await gw.get_favorite("script", model.target_id)
        assert result is not None
        assert result.target_type == "script"

    @pytest.mark.asyncio
    async def test_get_favorite_not_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await gw.get_favorite("script", uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_remove_favorite_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)
        model = FavoriteModel(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            note=None,
            created_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute.return_value = mock_result

        result = await gw.remove_favorite("command", model.target_id)
        assert result is True
        session.delete.assert_awaited_once_with(model)

    @pytest.mark.asyncio
    async def test_remove_favorite_not_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await gw.remove_favorite("command", uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_list_favorites_with_type(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)
        model = FavoriteModel(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            note=None,
            created_at=datetime.now(UTC),
        )

        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [model]
        session.execute.side_effect = [count_result, rows_result]

        items, total = await gw.list_favorites("command", 0, 10)
        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_favorites_no_type(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyFavoriteGateway(session)

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, rows_result]

        items, total = await gw.list_favorites(None, 0, 10)
        assert total == 0
        assert len(items) == 0


# ─── Note adapter ───


class TestNoteGateway:
    @pytest.mark.asyncio
    async def test_create_note(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        data = NoteCreateDTO(
            target_type="node",
            target_id=uuid.uuid4(),
            content="Check this",
        )
        result = await gw.create_note(data)
        assert isinstance(result, NoteDTO)
        assert result.content == "Check this"
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_note_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        model = NoteModel(
            id=uuid.uuid4(),
            target_type="node",
            target_id=uuid.uuid4(),
            content="Hello",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute.return_value = mock_result

        result = await gw.get_note(model.id)
        assert result is not None
        assert result.content == "Hello"

    @pytest.mark.asyncio
    async def test_get_note_not_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await gw.get_note(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_note_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        model = NoteModel(
            id=uuid.uuid4(),
            target_type="node",
            target_id=uuid.uuid4(),
            content="old",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute.return_value = mock_result

        result = await gw.update_note(model.id, NoteUpdateDTO(content="new"))
        assert result is not None
        assert model.content == "new"

    @pytest.mark.asyncio
    async def test_update_note_not_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await gw.update_note(uuid.uuid4(), NoteUpdateDTO(content="x"))
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_note_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        model = NoteModel(
            id=uuid.uuid4(),
            target_type="node",
            target_id=uuid.uuid4(),
            content="del",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        session.execute.return_value = mock_result

        result = await gw.delete_note(model.id)
        assert result is True
        session.delete.assert_awaited_once_with(model)

    @pytest.mark.asyncio
    async def test_delete_note_not_found(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await gw.delete_note(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_list_notes(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyNoteGateway(session)
        model = NoteModel(
            id=uuid.uuid4(),
            target_type="command",
            target_id=uuid.uuid4(),
            content="note",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        session.execute.return_value = mock_result

        result = await gw.list_notes("command", model.target_id)
        assert len(result) == 1


# ─── Tag manager adapter ───


class TestTagManager:
    @pytest.mark.asyncio
    async def test_rename_tag(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyTagManager(session)
        mock_result = MagicMock()
        mock_result.rowcount = 2
        session.execute.return_value = mock_result

        # Mock func.array_cat and func.array to avoid subscript error
        with patch("app.adapters.persistence.tag_manager.func") as mock_func:
            mock_func.array_remove.return_value = "removed"
            mock_func.array.__getitem__ = MagicMock(return_value="arr")
            mock_func.array_cat.return_value = "cat"
            result = await gw.rename_tag("old", "new")
        assert result == 6  # 2 rows * 3 models
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_tag(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyTagManager(session)
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute.return_value = mock_result

        result = await gw.delete_tag("toremove")
        assert result == 3  # 1 row * 3 models
        session.flush.assert_awaited_once()


# ─── Execution stats gateway ───


class TestExecutionStatsGateway:
    @pytest.mark.asyncio
    async def test_to_stats_dto_with_data(self) -> None:
        row = {
            "total": 10,
            "successful": 8,
            "failed": 2,
            "avg_duration_ms": 150.0,
            "min_duration_ms": 50.0,
            "max_duration_ms": 300.0,
            "last_executed_at": datetime.now(UTC),
        }
        result = SqlAlchemyExecutionStatsGateway._to_stats_dto(row)
        assert isinstance(result, ExecutionStatsDTO)
        assert result.total == 10
        assert result.successful == 8
        assert result.failed == 2
        assert result.success_rate == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_to_stats_dto_empty(self) -> None:
        row = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "avg_duration_ms": None,
            "min_duration_ms": None,
            "max_duration_ms": None,
            "last_executed_at": None,
        }
        result = SqlAlchemyExecutionStatsGateway._to_stats_dto(row)
        assert result.total == 0
        assert result.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_command_stats(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock(return_value=session_ctx)

        gw = SqlAlchemyExecutionStatsGateway(sm)
        row = {
            "total": 5,
            "successful": 4,
            "failed": 1,
            "avg_duration_ms": 100.0,
            "min_duration_ms": 50.0,
            "max_duration_ms": 200.0,
            "last_executed_at": datetime.now(UTC),
        }
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = MagicMock(_mapping=row)
        session.execute.return_value = mock_result

        result = await gw.get_command_stats(
            CommandStatsQueryDTO(command_id=uuid.uuid4())
        )
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_get_script_stats(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock(return_value=session_ctx)

        gw = SqlAlchemyExecutionStatsGateway(sm)
        row = {
            "total": 3,
            "successful": 3,
            "failed": 0,
            "avg_duration_ms": 80.0,
            "min_duration_ms": 60.0,
            "max_duration_ms": 100.0,
            "last_executed_at": datetime.now(UTC),
        }
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = MagicMock(_mapping=row)
        session.execute.return_value = mock_result

        result = await gw.get_script_stats(ScriptStatsQueryDTO(script_id=uuid.uuid4()))
        assert result.total == 3

    @pytest.mark.asyncio
    async def test_get_node_command_stats_delegates(self) -> None:
        gw = SqlAlchemyExecutionStatsGateway(MagicMock())
        with patch.object(gw, "get_command_stats", new_callable=AsyncMock) as mock:
            mock.return_value = ExecutionStatsDTO(
                total=1,
                successful=1,
                failed=0,
                success_rate=1.0,
                avg_duration_ms=10,
                min_duration_ms=10,
                max_duration_ms=10,
                last_executed_at=None,
            )
            result = await gw.get_node_command_stats(
                CommandStatsQueryDTO(node_id=uuid.uuid4())
            )
            mock.assert_awaited_once()
            assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_node_script_stats_delegates(self) -> None:
        gw = SqlAlchemyExecutionStatsGateway(MagicMock())
        with patch.object(gw, "get_script_stats", new_callable=AsyncMock) as mock:
            mock.return_value = ExecutionStatsDTO(
                total=2,
                successful=1,
                failed=1,
                success_rate=0.5,
                avg_duration_ms=20,
                min_duration_ms=10,
                max_duration_ms=30,
                last_executed_at=None,
            )
            result = await gw.get_node_script_stats(
                ScriptStatsQueryDTO(node_id=uuid.uuid4())
            )
            mock.assert_awaited_once()
            assert result.total == 2


# ─── Global search gateway ───


class TestGlobalSearchGateway:
    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        session = AsyncMock()
        sessionmaker = MagicMock()
        sessionmaker.return_value.__aenter__ = AsyncMock(return_value=session)
        sessionmaker.return_value.__aexit__ = AsyncMock(return_value=False)
        gw = SqlAlchemyGlobalSearchGateway(sessionmaker)

        node_row = MagicMock()
        node_row.id = uuid.uuid4()
        node_row.name = "web-01"

        cmd_row = MagicMock()
        cmd_row.id = uuid.uuid4()
        cmd_row.name = "deploy"

        script_row = MagicMock()
        script_row.id = uuid.uuid4()
        script_row.name = "backup"

        tag_row = MagicMock()
        tag_row.tag = "production"

        mock_node = MagicMock()
        mock_node.all.return_value = [node_row]
        mock_cmd = MagicMock()
        mock_cmd.all.return_value = [cmd_row]
        mock_script = MagicMock()
        mock_script.all.return_value = [script_row]
        mock_tag = MagicMock()
        mock_tag.all.return_value = [tag_row]

        session.execute.side_effect = [mock_node, mock_cmd, mock_script, mock_tag]

        result = await gw.search(GlobalSearchQueryDTO(q="web", limit=10))
        assert isinstance(result, GlobalSearchResultDTO)
        assert len(result.nodes) == 1
        assert len(result.commands) == 1
        assert len(result.scripts) == 1
        assert len(result.tags) == 1

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        session = AsyncMock()
        sessionmaker = MagicMock()
        sessionmaker.return_value.__aenter__ = AsyncMock(return_value=session)
        sessionmaker.return_value.__aexit__ = AsyncMock(return_value=False)
        gw = SqlAlchemyGlobalSearchGateway(sessionmaker)

        empty = MagicMock()
        empty.all.return_value = []
        session.execute.side_effect = [empty, empty, empty, empty]

        result = await gw.search(GlobalSearchQueryDTO(q="nonexistent", limit=10))
        assert len(result.nodes) == 0
        assert len(result.commands) == 0
        assert len(result.scripts) == 0
        assert len(result.tags) == 0


# ─── Audit export gateway ───


class TestAuditExportGateway:
    @pytest.mark.asyncio
    async def test_export_audit_no_filters(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyAuditExporter(session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        result = await gw.export_audit(AuditExportQueryDTO())
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_export_audit_with_data(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyAuditExporter(session)

        log_model = MagicMock()
        log_model.id = uuid.uuid4()
        log_model.action = "node.create"
        log_model.node_id = "some-id"
        log_model.user = "admin"
        log_model.details = "{}"
        log_model.created_at = datetime.now(UTC)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [log_model]
        session.execute.return_value = mock_result

        result = await gw.export_audit(AuditExportQueryDTO())
        assert len(result) == 1
        assert isinstance(result[0], AuditExportRowDTO)
        assert result[0].action == "node.create"

    @pytest.mark.asyncio
    async def test_export_audit_with_filters(self) -> None:
        session = AsyncMock()
        gw = SqlAlchemyAuditExporter(session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        from datetime import UTC, datetime

        result = await gw.export_audit(
            AuditExportQueryDTO(
                date_from=datetime(2025, 1, 1, tzinfo=UTC),
                date_to=datetime(2025, 12, 31, tzinfo=UTC),
                action="node.create",
                node_id=uuid.uuid4(),
            )
        )
        assert isinstance(result, list)
        assert session.execute.called


class TestDashboardMetricsDAO:
    @pytest.mark.asyncio
    async def test_command_metrics_empty(self) -> None:
        session = AsyncMock()
        repo = DashboardMetricsRepository(session)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        from app.application.dto.dashboard_metrics import MetricsQueryDTO

        result = await repo.command_metrics(MetricsQueryDTO(group_by="day"))
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_script_metrics_empty(self) -> None:
        session = AsyncMock()
        repo = DashboardMetricsRepository(session)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        session.execute.return_value = mock_result

        from app.application.dto.dashboard_metrics import MetricsQueryDTO

        result = await repo.script_metrics(MetricsQueryDTO(group_by="hour"))
        assert isinstance(result, list)


# ─── Execution stats DAO ───


class TestExecutionStatsDAO:
    @pytest.mark.asyncio
    async def test_command_stats(self) -> None:
        session = AsyncMock()
        repo = ExecutionStatsRepository(session)
        row = {
            "total": 5,
            "successful": 4,
            "failed": 1,
            "avg_duration_ms": 100.0,
            "min_duration_ms": 50.0,
            "max_duration_ms": 200.0,
            "last_executed_at": datetime.now(UTC),
        }
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = MagicMock(_mapping=row)
        session.execute.return_value = mock_result

        result = await repo.command_stats(command_id=uuid.uuid4())
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_script_stats(self) -> None:
        session = AsyncMock()
        repo = ExecutionStatsRepository(session)
        row = {
            "total": 3,
            "successful": 3,
            "failed": 0,
            "avg_duration_ms": 80.0,
            "min_duration_ms": 60.0,
            "max_duration_ms": 100.0,
            "last_executed_at": datetime.now(UTC),
        }
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = MagicMock(_mapping=row)
        session.execute.return_value = mock_result

        result = await repo.script_stats(script_id=uuid.uuid4())
        assert result["total"] == 3


# ─── Node status history DAO ───


class TestNodeStatusHistoryDAO:
    @pytest.mark.asyncio
    async def test_create(self) -> None:
        session = AsyncMock()
        repo = NodeStatusHistoryRepository(session)
        data = {
            "node_id": uuid.uuid4(),
            "old_status": "active",
            "new_status": "unreachable",
            "source": "health_check",
        }
        result = await repo.create(data)
        assert isinstance(result, NodeStatusHistoryModel)
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_by_node(self) -> None:
        session = AsyncMock()
        repo = NodeStatusHistoryRepository(session)
        model = NodeStatusHistoryModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            old_status="active",
            new_status="unreachable",
            source="check",
            changed_at=datetime.now(UTC),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        session.execute.return_value = mock_result

        result = await repo.list_by_node(model.node_id)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_by_node(self) -> None:
        session = AsyncMock()
        repo = NodeStatusHistoryRepository(session)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        session.execute.return_value = mock_result

        result = await repo.count_by_node(uuid.uuid4())
        assert result == 5


# ─── Node status history gateway ───


class TestNodeStatusHistoryGateway:
    @pytest.mark.asyncio
    async def test_save(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyNodeStatusHistoryGateway(sm)
        data = NodeStatusChangeDTO(
            node_id=uuid.uuid4(),
            old_status="active",
            new_status="unreachable",
            source="check",
        )
        await gw.save(data)
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_by_node(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.return_value = session_ctx  # __call__ for sessionmaker()

        gw = SqlAlchemyNodeStatusHistoryGateway(sm)

        model = NodeStatusHistoryModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            old_status="active",
            new_status="unreachable",
            source="check",
            changed_at=datetime.now(UTC),
        )
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [model]
        session.execute.side_effect = [list_result, count_result]

        query = NodeStatusHistoryQueryDTO(node_id=model.node_id, offset=0, limit=10)
        result = await gw.list_by_node(query)
        assert isinstance(result, NodeStatusHistoryPageDTO)
        assert result.total == 1
        assert len(result.items) == 1


# ─── Execution lifecycle gateway ───


class TestExecutionLifecycleGateway:
    @pytest.mark.asyncio
    async def test_cancel_command_execution(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyExecutionLifecycleGateway(sm)
        exec_id = uuid.uuid4()

        from app.application.dto.execution_lifecycle import CancelExecutionDTO

        cmd_repo = MagicMock()
        cmd_repo.get_by_id = AsyncMock(return_value=MagicMock())

        with patch(
            "app.adapters.persistence.execution_lifecycle.CommandExecutionRepository",
            return_value=cmd_repo,
        ):
            result = await gw.cancel_execution(CancelExecutionDTO(execution_id=exec_id))
            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_script_execution_running(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyExecutionLifecycleGateway(sm)
        exec_id = uuid.uuid4()

        from app.application.dto.execution_lifecycle import CancelExecutionDTO

        cmd_repo = MagicMock()
        cmd_repo.get_by_id = AsyncMock(return_value=None)
        script_repo = MagicMock()
        script_model = MagicMock()
        script_model.status = "running"
        script_repo.get_by_id = AsyncMock(return_value=script_model)
        script_repo.update = AsyncMock()

        with (
            patch(
                "app.adapters.persistence.execution_lifecycle.CommandExecutionRepository",
                return_value=cmd_repo,
            ),
            patch(
                "app.adapters.persistence.execution_lifecycle.ScriptExecutionRepository",
                return_value=script_repo,
            ),
        ):
            result = await gw.cancel_execution(CancelExecutionDTO(execution_id=exec_id))
            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_script_execution_completed(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyExecutionLifecycleGateway(sm)
        exec_id = uuid.uuid4()

        from app.application.dto.execution_lifecycle import CancelExecutionDTO

        cmd_repo = MagicMock()
        cmd_repo.get_by_id = AsyncMock(return_value=None)
        script_repo = MagicMock()
        script_model = MagicMock()
        script_model.status = "completed"
        script_repo.get_by_id = AsyncMock(return_value=script_model)

        with (
            patch(
                "app.adapters.persistence.execution_lifecycle.CommandExecutionRepository",
                return_value=cmd_repo,
            ),
            patch(
                "app.adapters.persistence.execution_lifecycle.ScriptExecutionRepository",
                return_value=script_repo,
            ),
        ):
            result = await gw.cancel_execution(CancelExecutionDTO(execution_id=exec_id))
            assert result is False

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_execution(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock()
        sm.begin.return_value = session_ctx

        gw = SqlAlchemyExecutionLifecycleGateway(sm)

        from app.application.dto.execution_lifecycle import CancelExecutionDTO

        cmd_repo = MagicMock()
        cmd_repo.get_by_id = AsyncMock(return_value=None)
        script_repo = MagicMock()
        script_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "app.adapters.persistence.execution_lifecycle.CommandExecutionRepository",
                return_value=cmd_repo,
            ),
            patch(
                "app.adapters.persistence.execution_lifecycle.ScriptExecutionRepository",
                return_value=script_repo,
            ),
        ):
            result = await gw.cancel_execution(
                CancelExecutionDTO(execution_id=uuid.uuid4())
            )
            assert result is False
