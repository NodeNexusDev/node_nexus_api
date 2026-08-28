"""Comprehensive unit tests for DAO queries, scheduler adapter, streaming service,
and node management cursor pagination."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.persistence.audit_export import SqlAlchemyAuditExporter
from app.adapters.persistence.dao.dashboard_metrics import DashboardMetricsRepository
from app.adapters.persistence.dao.execution_stats import (
    _DEFAULT_STATS,
    ExecutionStatsRepository,
)
from app.adapters.runtime.scheduler import ApschedulerJobScheduler
from app.application.dto.dashboard_metrics import MetricsQueryDTO
from app.application.dto.export import AuditExportQueryDTO, AuditExportRowDTO
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.node_management import NodeCursorQueryDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.schedule import RuntimeJobViewDTO, RuntimeScheduleDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_management_service import NodeManagementService
from app.application.services.streaming_command_service import StreamingCommandService
from app.core.exceptions import NodeNotFoundError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(**cols: Any) -> Any:
    """Create a named-row mock mimicking a SQLAlchemy Row object."""
    return SimpleNamespace(**cols, _mapping=cols)


# ===========================================================================
# ExecutionStatsRepository
# ===========================================================================


def _mock_session_with_result(result: Any) -> AsyncMock:
    """Return an AsyncMock session whose execute() resolves to *result*."""
    session = AsyncMock()
    session.execute.return_value = result
    return session


class TestCommandStats:
    async def test_all_filters_produce_correct_where(self) -> None:
        row = _make_row(
            total=5,
            successful=4,
            failed=1,
            avg_duration_ms=120.5,
            min_duration_ms=80.0,
            max_duration_ms=200.0,
            last_executed_at=datetime(2026, 3, 15, tzinfo=UTC),
        )
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = row
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)
        cmd_id = uuid.uuid4()
        node_id = uuid.uuid4()
        dt_from = datetime(2026, 1, 1, tzinfo=UTC)
        dt_to = datetime(2026, 6, 1, tzinfo=UTC)

        result = await repo.command_stats(
            command_id=cmd_id,
            node_id=node_id,
            date_from=dt_from,
            date_to=dt_to,
        )

        call_args = session.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "ce.command_id = :command_id" in str(sql)
        assert "ce.node_id = :node_id" in str(sql)
        assert "ce.started_at >= :date_from" in str(sql)
        assert "ce.started_at <= :date_to" in str(sql)
        assert params["command_id"] == cmd_id
        assert params["node_id"] == node_id
        assert params["date_from"] == dt_from
        assert params["date_to"] == dt_to
        assert result["total"] == 5
        assert result["successful"] == 4

    async def test_no_filters_where_true(self) -> None:
        row = _make_row(
            total=10,
            successful=8,
            failed=2,
            avg_duration_ms=99.0,
            min_duration_ms=10.0,
            max_duration_ms=500.0,
            last_executed_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = row
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)

        result = await repo.command_stats()

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "TRUE" in sql
        assert params == {}
        assert result["total"] == 10

    async def test_returns_default_stats_when_no_row(self) -> None:
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = None
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)

        result = await repo.command_stats(command_id=uuid.uuid4())

        assert result == dict(_DEFAULT_STATS)

    async def test_partial_filters(self) -> None:
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = None
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)

        await repo.command_stats(node_id=uuid.uuid4())

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "ce.node_id = :node_id" in sql
        assert "ce.command_id" not in sql
        assert len(params) == 1


class TestScriptStats:
    async def test_all_filters_produce_correct_where(self) -> None:
        row = _make_row(
            total=3,
            successful=2,
            failed=1,
            avg_duration_ms=250.0,
            min_duration_ms=100.0,
            max_duration_ms=400.0,
            last_executed_at=datetime(2026, 4, 10, tzinfo=UTC),
        )
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = row
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)
        script_id = uuid.uuid4()
        node_id = uuid.uuid4()
        dt_from = datetime(2026, 2, 1, tzinfo=UTC)
        dt_to = datetime(2026, 7, 1, tzinfo=UTC)

        result = await repo.script_stats(
            script_id=script_id,
            node_id=node_id,
            date_from=dt_from,
            date_to=dt_to,
        )

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]

        assert "se.script_id = :script_id" in sql
        assert "se.node_id = :node_id" in sql
        assert "se.started_at >= :date_from" in sql
        assert "se.started_at <= :date_to" in sql
        assert params["script_id"] == script_id
        assert params["node_id"] == node_id
        assert params["date_from"] == dt_from
        assert params["date_to"] == dt_to
        assert result["total"] == 3
        assert "se.status IN ('success', 'completed')" in sql
        assert "se.status IN ('error', 'failed')" in sql
        assert "se.status !=" not in sql

    async def test_no_filters_where_true(self) -> None:
        row = _make_row(
            total=7,
            successful=6,
            failed=1,
            avg_duration_ms=150.0,
            min_duration_ms=30.0,
            max_duration_ms=300.0,
            last_executed_at=datetime(2026, 6, 1, tzinfo=UTC),
        )
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = row
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)

        result = await repo.script_stats()

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "TRUE" in sql
        assert params == {}
        assert result["total"] == 7

    async def test_returns_default_when_no_row(self) -> None:
        execute_result = MagicMock()
        execute_result.one_or_none.return_value = None
        session = _mock_session_with_result(execute_result)
        repo = ExecutionStatsRepository(session)

        result = await repo.script_stats(script_id=uuid.uuid4())

        assert result == dict(_DEFAULT_STATS)


# ===========================================================================
# DashboardMetricsRepository
# ===========================================================================


class TestCommandMetrics:
    async def test_date_filters_add_where_clauses(self) -> None:
        row = SimpleNamespace(
            period=datetime(2026, 3, 1, tzinfo=UTC),
            total=50,
            successful=45,
            failed=5,
            avg_duration_ms=200.0,
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [row]
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        dt_from = datetime(2026, 1, 1, tzinfo=UTC)
        dt_to = datetime(2026, 12, 31, tzinfo=UTC)
        query = MetricsQueryDTO(date_from=dt_from, date_to=dt_to, group_by="day")

        result = await repo.command_metrics(query)

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]

        assert "ce.started_at >= :date_from" in sql
        assert "ce.started_at <= :date_to" in sql
        assert params["date_from"] == dt_from
        assert params["date_to"] == dt_to
        assert params["grp"] == "day"
        assert len(result) == 1
        assert result[0].total == 50

    async def test_no_filters_where_true(self) -> None:
        execute_result = MagicMock()
        execute_result.all.return_value = []
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        query = MetricsQueryDTO(group_by="hour")

        result = await repo.command_metrics(query)

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "TRUE" in sql
        assert params["grp"] == "hour"
        assert result == []

    async def test_week_group_by(self) -> None:
        execute_result = MagicMock()
        execute_result.all.return_value = []
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        query = MetricsQueryDTO(group_by="week")

        await repo.command_metrics(query)

        params = session.execute.call_args[0][1]
        assert params["grp"] == "week"

    async def test_month_group_by(self) -> None:
        execute_result = MagicMock()
        execute_result.all.return_value = []
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        query = MetricsQueryDTO(group_by="month")

        await repo.command_metrics(query)

        params = session.execute.call_args[0][1]
        assert params["grp"] == "month"


class TestScriptMetrics:
    async def test_date_filters_add_where_clauses(self) -> None:
        row = SimpleNamespace(
            period=datetime(2026, 5, 1, tzinfo=UTC),
            total=30,
            successful=28,
            failed=2,
            avg_duration_ms=180.0,
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [row]
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        dt_from = datetime(2026, 4, 1, tzinfo=UTC)
        dt_to = datetime(2026, 8, 1, tzinfo=UTC)
        query = MetricsQueryDTO(date_from=dt_from, date_to=dt_to, group_by="day")

        result = await repo.script_metrics(query)

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]

        assert "se.started_at >= :date_from" in sql
        assert "se.started_at <= :date_to" in sql
        assert params["date_from"] == dt_from
        assert params["date_to"] == dt_to
        assert len(result) == 1
        assert result[0].avg_duration_ms == 180.0
        assert "se.status IN ('success', 'completed')" in sql
        assert "se.status IN ('error', 'failed')" in sql
        assert "se.status !=" not in sql

    async def test_no_filters_where_true(self) -> None:
        execute_result = MagicMock()
        execute_result.all.return_value = []
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        query = MetricsQueryDTO(group_by="day")

        result = await repo.script_metrics(query)

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        assert "TRUE" in sql
        assert result == []

    async def test_partial_filters_only_date_from(self) -> None:
        execute_result = MagicMock()
        execute_result.all.return_value = []
        session = _mock_session_with_result(execute_result)
        repo = DashboardMetricsRepository(session)
        dt_from = datetime(2026, 1, 1, tzinfo=UTC)
        query = MetricsQueryDTO(date_from=dt_from, group_by="hour")

        await repo.script_metrics(query)

        call_args = session.execute.call_args
        sql = str(call_args[0][0])
        params = call_args[0][1]
        assert "se.started_at >= :date_from" in sql
        assert "se.started_at <= :date_to" not in sql
        assert "date_to" not in params


# ===========================================================================
# SqlAlchemyAuditExporter
# ===========================================================================


class TestAuditExport:
    async def test_all_filters_applied(self) -> None:
        log1 = SimpleNamespace(
            id=uuid.uuid4(),
            action="create",
            node_id=uuid.uuid4(),
            user="admin",
            details='{"name":"s1"}',
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [log1]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session = _mock_session_with_result(execute_result)
        exporter = SqlAlchemyAuditExporter(session)

        query = AuditExportQueryDTO(
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to=datetime(2026, 6, 1, tzinfo=UTC),
            action="create",
            node_id=uuid.uuid4(),
        )
        result = await exporter.export_audit(query)

        assert len(result) == 1
        assert isinstance(result[0], AuditExportRowDTO)
        assert result[0].action == "create"

    async def test_no_filters_returns_all(self) -> None:
        log1 = SimpleNamespace(
            id=uuid.uuid4(),
            action="delete",
            node_id=None,
            user="ops",
            details=None,
            created_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [log1]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session = _mock_session_with_result(execute_result)
        exporter = SqlAlchemyAuditExporter(session)

        result = await exporter.export_audit(AuditExportQueryDTO())

        assert len(result) == 1
        assert result[0].node_id is None
        assert result[0].user == "ops"

    async def test_empty_result(self) -> None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session = _mock_session_with_result(execute_result)
        exporter = SqlAlchemyAuditExporter(session)

        result = await exporter.export_audit(AuditExportQueryDTO())

        assert result == []

    async def test_row_dto_fields_mapping(self) -> None:
        log = SimpleNamespace(
            id=uuid.uuid4(),
            action="update",
            node_id=uuid.uuid4(),
            user="admin",
            details='{"key":"val"}',
            created_at=datetime(2026, 7, 10, 14, 30, tzinfo=UTC),
        )
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [log]
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session = _mock_session_with_result(execute_result)
        exporter = SqlAlchemyAuditExporter(session)

        result = await exporter.export_audit(AuditExportQueryDTO())

        row = result[0]
        assert row.id == str(log.id)
        assert row.action == "update"
        assert row.node_id == str(log.node_id)
        assert row.user == "admin"
        assert row.details == '{"key":"val"}'

    async def test_node_id_filter_converts_to_str(self) -> None:
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_mock
        session = _mock_session_with_result(execute_result)
        exporter = SqlAlchemyAuditExporter(session)

        nid = uuid.uuid4()
        await exporter.export_audit(AuditExportQueryDTO(node_id=nid))

        stmt = session.execute.call_args[0][0]
        params = stmt.compile().params
        assert str(nid) in str(params)


# ===========================================================================
# ApschedulerJobScheduler
# ===========================================================================


class TestSchedulerValidate:
    def test_valid_cron_no_error(self) -> None:
        adapter = ApschedulerJobScheduler(MagicMock())
        adapter.validate("0 9 * * *", "UTC")

    def test_invalid_cron_raises(self) -> None:
        adapter = ApschedulerJobScheduler(MagicMock())
        with pytest.raises(Exception):
            adapter.validate("not_a_cron", "UTC")


class TestSchedulerAddOrReplace:
    def test_calls_schedule_script_and_returns_dto(self) -> None:
        scheduler = MagicMock()
        next_run = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
        scheduler.get_next_run_time.return_value = next_run
        adapter = ApschedulerJobScheduler(scheduler)

        schedule_id = uuid.uuid4()
        script_id = uuid.uuid4()
        node_id = uuid.uuid4()

        result = adapter.add_or_replace(
            RuntimeScheduleDTO(
                schedule_id=schedule_id,
                script_id=script_id,
                cron="30 8 * * *",
                timezone="Europe/Moscow",
                node_ids=(node_id,),
                params=(("env", "staging"),),
                misfire_grace_seconds=120,
            )
        )

        scheduler.schedule_script.assert_called_once_with(
            script_id,
            "30 8 * * *",
            [node_id],
            params={"env": "staging"},
            timezone="Europe/Moscow",
            misfire_grace_seconds=120,
            schedule_id=schedule_id,
        )
        assert isinstance(result, RuntimeJobViewDTO)
        assert result.script_id == script_id
        assert result.next_run_at == next_run


class TestSchedulerRemove:
    def test_delegates_to_unschedule_script(self) -> None:
        scheduler = MagicMock()
        scheduler.unschedule_script.return_value = True
        adapter = ApschedulerJobScheduler(scheduler)
        sid = uuid.uuid4()

        assert adapter.remove(sid) is True
        scheduler.unschedule_script.assert_called_once_with(sid)

    def test_returns_false_when_not_found(self) -> None:
        scheduler = MagicMock()
        scheduler.unschedule_script.return_value = False
        adapter = ApschedulerJobScheduler(scheduler)

        assert adapter.remove(uuid.uuid4()) is False


class TestSchedulerInspect:
    def test_returns_list_of_job_dtos(self) -> None:
        scheduler = MagicMock()
        sid = uuid.uuid4()
        next_run = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        scheduler.list_schedules.return_value = [
            {"job_id": str(sid), "next_run_time": next_run.isoformat()},
        ]
        adapter = ApschedulerJobScheduler(scheduler)

        result = adapter.inspect()

        assert len(result) == 1
        assert result[0].script_id == sid
        assert result[0].next_run_at == datetime.fromisoformat(next_run.isoformat())

    def test_empty_schedules(self) -> None:
        scheduler = MagicMock()
        scheduler.list_schedules.return_value = []
        adapter = ApschedulerJobScheduler(scheduler)

        assert adapter.inspect() == []


class TestSchedulerParseDatetime:
    def test_datetime_input_returned_as_is(self) -> None:
        dt = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        assert ApschedulerJobScheduler._parse_datetime(dt) is dt

    def test_string_input_parsed(self) -> None:
        s = "2026-05-01T12:00:00+00:00"
        result = ApschedulerJobScheduler._parse_datetime(s)
        assert isinstance(result, datetime)
        assert result.hour == 12

    def test_none_returns_none(self) -> None:
        assert ApschedulerJobScheduler._parse_datetime(None) is None

    def test_other_type_returns_none(self) -> None:
        assert ApschedulerJobScheduler._parse_datetime(42) is None
        assert ApschedulerJobScheduler._parse_datetime([1, 2]) is None

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            ApschedulerJobScheduler._parse_datetime("")


class TestSchedulerReadinessAndOwnership:
    def test_is_ready(self) -> None:
        scheduler = MagicMock(ready=True, owns_execution=False)
        adapter = ApschedulerJobScheduler(scheduler)
        assert adapter.is_ready() is True

    def test_owns_execution(self) -> None:
        scheduler = MagicMock(ready=False, owns_execution=True)
        adapter = ApschedulerJobScheduler(scheduler)
        assert adapter.owns_execution() is True


class TestSchedulerMarkRestored:
    def test_delegates_to_scheduler(self) -> None:
        scheduler = MagicMock()
        adapter = ApschedulerJobScheduler(scheduler)
        adapter.mark_restored(failed=3)
        scheduler.mark_restored.assert_called_once_with(failed=3)


# ===========================================================================
# StreamingCommandService
# ===========================================================================


class TestStreamingConnect:
    async def test_node_found_yields_session(self) -> None:
        node_id = uuid.uuid4()
        reader = AsyncMock()
        reader.get_connection.return_value = NodeConnectionDTO(
            id=node_id,
            name="n",
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="root"),
        )
        connector = AsyncMock()
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        cipher = MagicMock()
        cipher.decrypt.side_effect = lambda v: v

        service = StreamingCommandService(reader, factory, cipher)

        async with service.connect(node_id) as session:
            connector.connect.assert_awaited_once()
            from app.application.services.streaming_command_service import (
                StreamingCommandSession,
            )

            assert isinstance(session, StreamingCommandSession)

        connector.disconnect.assert_awaited_once()

    async def test_node_not_found_raises(self) -> None:
        reader = AsyncMock()
        reader.get_connection.return_value = None
        factory = MagicMock()
        cipher = MagicMock()

        service = StreamingCommandService(reader, factory, cipher)

        with pytest.raises(NodeNotFoundError):
            async with service.connect(uuid.uuid4()):
                pass

        factory.create_ssh.assert_not_called()

    async def test_disconnect_called_on_exception(self) -> None:
        node_id = uuid.uuid4()
        reader = AsyncMock()
        reader.get_connection.return_value = NodeConnectionDTO(
            id=node_id,
            name="n",
            endpoint=NodeEndpoint(host="h", port=22, connection_type="ssh"),
            credentials=NodeCredentials(username="root"),
        )
        connector = AsyncMock()
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        cipher = MagicMock()
        cipher.decrypt.side_effect = lambda v: v

        service = StreamingCommandService(reader, factory, cipher)

        with pytest.raises(ValueError, match="boom"):
            async with service.connect(node_id):
                raise ValueError("boom")

        connector.disconnect.assert_awaited_once()

    async def test_credentials_passed_to_connector(self) -> None:
        node_id = uuid.uuid4()
        reader = AsyncMock()
        reader.get_connection.return_value = NodeConnectionDTO(
            id=node_id,
            name="n",
            endpoint=NodeEndpoint(host="10.0.0.1", port=2222, connection_type="ssh"),
            credentials=NodeCredentials(
                username="admin",
                password="enc_pw",
                ssh_key="enc_key",
                passphrase="enc_pass",
            ),
        )
        connector = AsyncMock()
        factory = MagicMock()
        factory.create_ssh.return_value = connector
        cipher = MagicMock()
        cipher.decrypt.side_effect = lambda v: f"dec_{v}"

        service = StreamingCommandService(reader, factory, cipher)

        async with service.connect(node_id):
            pass

        factory.create_ssh.assert_called_once_with(
            host="10.0.0.1",
            port=2222,
            username="admin",
            password="dec_enc_pw",
            ssh_key="dec_enc_key",
            passphrase="dec_enc_pass",
        )


# ===========================================================================
# NodeManagementService cursor pagination
# ===========================================================================


class TestGetNodesCursor:
    async def test_with_cursor_delegates_correctly(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()

        cursor_ts = datetime(2026, 6, 1, tzinfo=UTC)
        cursor_id = uuid.uuid4()
        cursor = (cursor_ts, cursor_id)

        node = NodeViewDTO(
            id=uuid.uuid4(),
            name="n",
            status="active",
            username="root",
            tags=(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            endpoint=NodeEndpoint(
                host="h", port=22, connection_type="ssh", docker_host=None
            ),
        )
        next_cursor = (datetime(2026, 7, 1, tzinfo=UTC), uuid.uuid4())
        reader.list_nodes_cursor.return_value = SimpleNamespace(
            items=(node,),
            next_cursor=next_cursor,
            has_more=True,
        )

        svc = NodeManagementService(reader, writer, cipher)
        items, nc, has_more = await svc.get_nodes_cursor(
            cursor=cursor,
            limit=10,
            tags=["web"],
            search="prod",
        )

        reader.list_nodes_cursor.assert_awaited_once()
        query = reader.list_nodes_cursor.call_args[0][0]
        assert isinstance(query, NodeCursorQueryDTO)
        assert query.cursor == cursor
        assert query.limit == 10
        assert query.tags == ("web",)
        assert query.search == "prod"
        assert len(items) == 1
        assert items[0].name == "n"
        assert nc == next_cursor
        assert has_more is True

    async def test_without_cursor_cursor_is_none(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()

        reader.list_nodes_cursor.return_value = SimpleNamespace(
            items=(),
            next_cursor=None,
            has_more=False,
        )

        svc = NodeManagementService(reader, writer, cipher)
        items, nc, has_more = await svc.get_nodes_cursor()

        query = reader.list_nodes_cursor.call_args[0][0]
        assert query.cursor is None
        assert query.limit == 20
        assert query.tags == ()
        assert query.search is None
        assert items == []
        assert nc is None
        assert has_more is False

    async def test_multiple_items(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        cipher = MagicMock()

        nodes = [
            NodeViewDTO(
                id=uuid.uuid4(),
                name=f"n{i}",
                status="active",
                username="root",
                tags=(),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                endpoint=NodeEndpoint(
                    host="h", port=22, connection_type="ssh", docker_host=None
                ),
            )
            for i in range(3)
        ]
        reader.list_nodes_cursor.return_value = SimpleNamespace(
            items=tuple(nodes),
            next_cursor=(datetime(2026, 8, 1, tzinfo=UTC), uuid.uuid4()),
            has_more=True,
        )

        svc = NodeManagementService(reader, writer, cipher)
        items, _, has_more = await svc.get_nodes_cursor(limit=3)

        assert len(items) == 3
        assert has_more is True
        assert items[0].name == "n0"
        assert items[2].name == "n2"
