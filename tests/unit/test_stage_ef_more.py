"""Additional tests for low-coverage DAOs and adapters — dashboard, bulk_operator,
command_execution, dashboard_metrics gateway, execution_stats gateway."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.dao.command_execution import (
    CommandExecutionRepository,
)
from app.adapters.persistence.dashboard import SqlAlchemyDashboardGateway
from app.adapters.persistence.dashboard_metrics import (
    SqlAlchemyDashboardMetricsGateway,
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
        mock_result = MagicMock()
        mock_result.rowcount = 2
        session.execute = AsyncMock(return_value=mock_result)

        result = await gw.bulk_delete(BulkNodeDeleteDTO(node_ids=(node_id1, node_id2)))
        assert result.affected == 2

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
        mock_update_result = MagicMock()
        session.execute = AsyncMock(
            side_effect=[mock_select_result, mock_update_result]
        )

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
        mock_update_result = MagicMock()
        session.execute = AsyncMock(
            side_effect=[mock_select_result, mock_update_result]
        )

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


# ─── Dashboard adapter ───


class TestDashboardGateway:
    @pytest.mark.asyncio
    async def test_get_dashboard_without_docker(self) -> None:
        sm = MagicMock()
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm.return_value = session_ctx

        gw = SqlAlchemyDashboardGateway(sm, node_reader=None, runtime=None)

        # Mock count queries
        count_results = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
        count_results[0].scalar_one.return_value = 5  # total nodes
        count_results[1].scalar_one.return_value = 3  # active
        count_results[2].scalar_one.return_value = 1  # unreachable
        count_results[3].scalar_one.return_value = 10  # scripts
        # We need one more for commands
        count_results.append(MagicMock())
        count_results[4].scalar_one.return_value = 8  # commands

        session.execute.side_effect = count_results

        # Mock audit for recent activity
        with patch.object(
            gw, "_recent_activity", new_callable=AsyncMock
        ) as mock_recent:
            mock_recent.return_value = ()
            result = await gw.get_dashboard()

        assert result.nodes.total == 5
        assert result.nodes.active == 3
        assert result.docker.total == 0  # no docker runtime

    @pytest.mark.asyncio
    async def test_count_docker_no_reader(self) -> None:
        sm = MagicMock()
        gw = SqlAlchemyDashboardGateway(sm, node_reader=None, runtime=None)
        result = await gw._count_docker()
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_count_docker_with_exception(self) -> None:
        sm = MagicMock()
        node_reader = AsyncMock()
        node_reader.get_connections_by_type = AsyncMock(side_effect=Exception("fail"))
        gw = SqlAlchemyDashboardGateway(
            sm, node_reader=node_reader, runtime=MagicMock()
        )
        result = await gw._count_docker()
        assert result.total == 0


# ─── DashboardMetricsGateway ───


class TestDashboardMetricsGateway:
    @pytest.mark.asyncio
    async def test_get_metrics(self) -> None:
        session = AsyncMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__.return_value = session
        session_ctx.__aexit__.return_value = False
        sm = MagicMock(return_value=session_ctx)

        gw = SqlAlchemyDashboardMetricsGateway(sm)

        from app.application.dto.dashboard_metrics import MetricsBucketDTO

        with patch(
            "app.adapters.persistence.dashboard_metrics.DashboardMetricsRepository"
        ) as mock_repo:
            repo = mock_repo.return_value
            repo.command_metrics = AsyncMock(
                return_value=[
                    MetricsBucketDTO(
                        period="2026-08-01",
                        total=10,
                        successful=8,
                        failed=2,
                        avg_duration_ms=100,
                    )
                ]
            )
            repo.script_metrics = AsyncMock(return_value=[])

            from app.application.dto.dashboard_metrics import MetricsQueryDTO

            result = await gw.get_metrics(MetricsQueryDTO(group_by="day"))
            assert len(result.command_metrics) == 1


# ─── Additional Dashboard tests ───


class TestDashboardGatewayDocker:
    @pytest.mark.asyncio
    async def test_count_docker_with_nodes(self) -> None:
        sm = MagicMock()
        node_reader = AsyncMock()
        node = MagicMock()
        node.id = uuid.uuid4()
        node.name = "docker-node"
        node_reader.get_connections_by_type = AsyncMock(return_value=[node])

        runtime = AsyncMock()
        exec_result = MagicMock()
        exec_result.exit_code = 0
        exec_result.stdout = '{"State":"running"}\n{"State":"stopped"}\n'
        runtime.execute = AsyncMock(return_value=exec_result)

        gw = SqlAlchemyDashboardGateway(sm, node_reader=node_reader, runtime=runtime)
        with (
            patch(
                "app.adapters.persistence.dashboard.build_docker_command",
                return_value="cmd",
            ),
            patch(
                "app.adapters.persistence.dashboard.parse_json_lines",
                return_value=[{"State": "running"}, {"State": "stopped"}],
            ),
            patch(
                "app.adapters.persistence.dashboard.json_string",
                side_effect=lambda d, k: d.get(k, ""),
            ),
        ):
            result = await gw._count_docker()
        assert result.total == 2
        assert result.running == 1
        assert result.stopped == 1

    @pytest.mark.asyncio
    async def test_count_docker_query_fails(self) -> None:
        sm = MagicMock()
        node_reader = AsyncMock()
        node = MagicMock()
        node.id = uuid.uuid4()
        node.name = "docker-node"
        node_reader.get_connections_by_type = AsyncMock(return_value=[node])

        runtime = AsyncMock()
        runtime.execute = AsyncMock(side_effect=Exception("timeout"))

        gw = SqlAlchemyDashboardGateway(sm, node_reader=node_reader, runtime=runtime)
        result = await gw._count_docker()
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_query_node_containers_non_zero_exit(self) -> None:
        sm = MagicMock()
        runtime = AsyncMock()
        exec_result = MagicMock()
        exec_result.exit_code = 1
        runtime.execute = AsyncMock(return_value=exec_result)

        gw = SqlAlchemyDashboardGateway(sm, runtime=runtime)
        node = MagicMock()
        with patch(
            "app.adapters.persistence.dashboard.build_docker_command",
            return_value="cmd",
        ):
            result = await gw._query_node_containers(node)
        assert result == {"total": 0, "running": 0, "stopped": 0}
