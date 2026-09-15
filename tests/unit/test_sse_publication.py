"""Unit tests for SSE event publication from application services.

Services publish to the in-memory SseBroadcaster (patched here);
the HTTP layer only streams whatever was published.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.script_execution import (
    ScriptExecutionRequestDTO,
    ScriptNodeResultDTO,
)
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.command_execution_service import CommandExecutionService
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_command_service import NodeCommandService
from app.application.services.schedule_management import ScheduleManagementService
from app.application.services.script_execution_service import ScriptExecutionService

NODE_ID = uuid.uuid4()
SCRIPT_ID = uuid.uuid4()


def _broadcaster():
    broadcaster = MagicMock()
    published: list[tuple[str, dict[str, Any]]] = []

    def _publish(event: str, data: dict[str, Any]) -> None:
        published.append((event, data))

    broadcaster.publish.side_effect = _publish
    return broadcaster, published


def _node_conn(uid, status="active"):
    conn = NodeConnectionDTO(
        id=uid,
        name="n",
        endpoint=NodeEndpoint(host="1.2.3.4", port=22),
        credentials=NodeCredentials(username="u", password="p"),
    )
    return conn


def _ok_connector():
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)
    mock_conn.execute_command = AsyncMock(return_value=("ok", "", 0))
    return mock_conn


class TestNodeStatusChanged:
    @pytest.mark.asyncio
    async def test_single_check_publishes_on_change(self) -> None:
        node_reader: Any = AsyncMock()
        status_writer: Any = AsyncMock()
        history_writer: Any = AsyncMock()
        view_reader: Any = AsyncMock()
        svc = NodeCommandService(
            node_reader=node_reader,
            status_writer=status_writer,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
            status_history_writer=history_writer,
            node_view_reader=view_reader,
        )
        node_reader.get_connection = AsyncMock(return_value=_node_conn(NODE_ID))
        view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="unreachable")
        )
        status_writer.update_node_status = AsyncMock(
            return_value=MagicMock(status="active")
        )
        broadcaster, published = _broadcaster()
        with (
            patch(
                "app.application.services.node_command_service.build_ssh_connector",
                return_value=_ok_connector(),
            ),
            patch(
                "app.application.services.sse_broadcaster.get_sse_broadcaster",
                return_value=broadcaster,
            ),
        ):
            await svc.check_connectivity(NODE_ID)
        assert published == [
            (
                "node.status_changed",
                {
                    "node_id": str(NODE_ID),
                    "old_status": "unreachable",
                    "new_status": "active",
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_single_check_skips_publish_without_change(self) -> None:
        node_reader: Any = AsyncMock()
        status_writer: Any = AsyncMock()
        history_writer: Any = AsyncMock()
        view_reader: Any = AsyncMock()
        svc = NodeCommandService(
            node_reader=node_reader,
            status_writer=status_writer,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
            status_history_writer=history_writer,
            node_view_reader=view_reader,
        )
        node_reader.get_connection = AsyncMock(return_value=_node_conn(NODE_ID))
        view_reader.get_node = AsyncMock(return_value=MagicMock(status="active"))
        status_writer.update_node_status = AsyncMock(
            return_value=MagicMock(status="active")
        )
        broadcaster, published = _broadcaster()
        with (
            patch(
                "app.application.services.node_command_service.build_ssh_connector",
                return_value=_ok_connector(),
            ),
            patch(
                "app.application.services.sse_broadcaster.get_sse_broadcaster",
                return_value=broadcaster,
            ),
        ):
            await svc.check_connectivity(NODE_ID)
        assert published == []

    @pytest.mark.asyncio
    async def test_bulk_check_publishes_on_change(self) -> None:
        node_reader: Any = AsyncMock()
        status_writer: Any = AsyncMock()
        history_writer: Any = AsyncMock()
        view_reader: Any = AsyncMock()
        svc = NodeBulkOperationService(
            operator=AsyncMock(),
            node_reader=node_reader,
            status_writer=status_writer,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
            status_history_writer=history_writer,
            node_view_reader=view_reader,
        )
        node_reader.get_connection = AsyncMock(return_value=_node_conn(NODE_ID))
        view_reader.get_node = AsyncMock(
            return_value=MagicMock(status="unreachable")
        )
        status_writer.update_node_status = AsyncMock(return_value=MagicMock())
        broadcaster, published = _broadcaster()
        with (
            patch(
                "app.application.services.ssh_executor.build_ssh_connector",
                return_value=_ok_connector(),
            ),
            patch(
                "app.application.services.sse_broadcaster.get_sse_broadcaster",
                return_value=broadcaster,
            ),
        ):
            result = await svc.bulk_check(node_ids=(str(NODE_ID),), mode="ssh")
        assert result.succeeded == 1
        assert published == [
            (
                "node.status_changed",
                {
                    "node_id": str(NODE_ID),
                    "old_status": "unreachable",
                    "new_status": "active",
                },
            )
        ]


class TestExecutionCompletedFailed:
    def _script_definition(self):
        return MagicMock(
            steps=[{"label": "s1", "type": "inline", "command": "echo hi"}],
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_script_success_publishes_completed(self) -> None:
        script_reader: Any = AsyncMock()
        execution_writer: Any = AsyncMock()
        exec_id = uuid.uuid4()
        script_reader.get_definition = AsyncMock(
            return_value=self._script_definition()
        )
        execution_writer.create_execution = AsyncMock(return_value=exec_id)
        svc = ScriptExecutionService(
            script_reader=script_reader,
            command_reader=AsyncMock(),
            node_reader=AsyncMock(),
            execution_writer=execution_writer,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
        )
        svc._resolve_targets = AsyncMock(  # type: ignore[method-assign]
            return_value=[_node_conn(NODE_ID)]
        )
        svc._run_remote = AsyncMock(  # type: ignore[method-assign]
            return_value=ScriptNodeResultDTO(
                execution_id=exec_id,
                node_id=NODE_ID,
                node_name="n",
                status="success",
                steps=(),
            )
        )
        broadcaster, published = _broadcaster()
        with patch(
            "app.application.services.sse_broadcaster.get_sse_broadcaster",
            return_value=broadcaster,
        ):
            await svc.execute_script(
                SCRIPT_ID, ScriptExecutionRequestDTO(node_ids=(NODE_ID,))
            )
        assert published == [
            (
                "execution.completed",
                {
                    "execution_id": str(exec_id),
                    "script_id": str(SCRIPT_ID),
                    "node_id": str(NODE_ID),
                    "status": "success",
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_script_error_publishes_failed(self) -> None:
        script_reader: Any = AsyncMock()
        execution_writer: Any = AsyncMock()
        exec_id = uuid.uuid4()
        script_reader.get_definition = AsyncMock(
            return_value=self._script_definition()
        )
        execution_writer.create_execution = AsyncMock(return_value=exec_id)
        svc = ScriptExecutionService(
            script_reader=script_reader,
            command_reader=AsyncMock(),
            node_reader=AsyncMock(),
            execution_writer=execution_writer,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
        )
        svc._resolve_targets = AsyncMock(  # type: ignore[method-assign]
            return_value=[_node_conn(NODE_ID)]
        )
        svc._run_remote = AsyncMock(  # type: ignore[method-assign]
            return_value=ScriptNodeResultDTO(
                execution_id=exec_id,
                node_id=NODE_ID,
                node_name="n",
                status="error",
                steps=(),
            )
        )
        broadcaster, published = _broadcaster()
        with patch(
            "app.application.services.sse_broadcaster.get_sse_broadcaster",
            return_value=broadcaster,
        ):
            await svc.execute_script(
                SCRIPT_ID, ScriptExecutionRequestDTO(node_ids=(NODE_ID,))
            )
        assert [e for e, _ in published] == ["execution.failed"]

    @pytest.mark.asyncio
    async def test_command_success_publishes_completed(self) -> None:
        command_id = uuid.uuid4()
        command_reader: Any = AsyncMock()
        node_reader: Any = AsyncMock()
        command_reader.get_template = AsyncMock(
            return_value=MagicMock(command="echo hi", parameters=[], timeout=30)
        )
        node_reader.get_connection = AsyncMock(return_value=_node_conn(NODE_ID))
        svc = CommandExecutionService(
            command_reader=command_reader,
            node_reader=node_reader,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
        )
        ssh_result = MagicMock(
            stdout="hi",
            stderr="",
            exit_code=0,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
        )
        broadcaster, published = _broadcaster()
        with (
            patch(
                "app.application.services.command_execution_service.build_ssh_connector",
                return_value=MagicMock(),
            ),
            patch(
                "app.application.services.command_execution_service.execute_ssh",
                AsyncMock(return_value=ssh_result),
            ),
            patch(
                "app.application.services.sse_broadcaster.get_sse_broadcaster",
                return_value=broadcaster,
            ),
        ):
            from app.application.dto.command_management import (
                CommandExecuteRequestDTO,
            )

            await svc.execute_command(
                command_id,
                CommandExecuteRequestDTO(node_id=NODE_ID, params=()),
            )
        assert published == [
            (
                "execution.completed",
                {
                    "command_id": str(command_id),
                    "node_id": str(NODE_ID),
                    "exit_code": 0,
                },
            )
        ]

    @pytest.mark.asyncio
    async def test_command_failure_publishes_failed(self) -> None:
        command_id = uuid.uuid4()
        command_reader: Any = AsyncMock()
        node_reader: Any = AsyncMock()
        command_reader.get_template = AsyncMock(
            return_value=MagicMock(command="echo hi", parameters=[], timeout=30)
        )
        node_reader.get_connection = AsyncMock(return_value=_node_conn(NODE_ID))
        svc = CommandExecutionService(
            command_reader=command_reader,
            node_reader=node_reader,
            credential_cipher=MagicMock(),
            connector_factory=MagicMock(),
        )
        broadcaster, published = _broadcaster()
        with (
            patch(
                "app.application.services.command_execution_service.build_ssh_connector",
                return_value=MagicMock(),
            ),
            patch(
                "app.application.services.command_execution_service.execute_ssh",
                AsyncMock(side_effect=RuntimeError("ssh down")),
            ),
            patch(
                "app.application.services.sse_broadcaster.get_sse_broadcaster",
                return_value=broadcaster,
            ),
        ):
            from app.application.dto.command_management import (
                CommandExecuteRequestDTO,
            )
            from app.core.exceptions import ConnectionFailedError

            with pytest.raises(ConnectionFailedError):
                await svc.execute_command(
                    command_id,
                    CommandExecuteRequestDTO(node_id=NODE_ID, params=()),
                )
        assert [e for e, _ in published] == ["execution.failed"]


class TestScriptScheduled:
    @pytest.mark.asyncio
    async def test_create_schedule_publishes_scheduled(self) -> None:
        reader: Any = AsyncMock()
        writer: Any = AsyncMock()
        script_reader: Any = AsyncMock()
        node_reader: Any = AsyncMock()
        scheduler: Any = MagicMock()
        script_reader.get_script = AsyncMock(return_value=MagicMock())
        node_reader.get_node = AsyncMock(return_value=MagicMock())
        writer.upsert_schedule = AsyncMock(return_value=MagicMock())
        scheduler.add_or_replace = MagicMock(
            return_value=MagicMock(next_run_at=None)
        )
        reader.get_schedule = AsyncMock(return_value=None)
        svc = ScheduleManagementService(
            reader=reader,
            writer=writer,
            script_reader=script_reader,
            node_reader=node_reader,
            scheduler=scheduler,
        )
        broadcaster, published = _broadcaster()
        with patch(
            "app.application.services.sse_broadcaster.get_sse_broadcaster",
            return_value=broadcaster,
        ):
            from app.application.dto.schedule import ScheduleRequestDTO

            await svc.create_or_update(
                SCRIPT_ID,
                ScheduleRequestDTO(
                    cron="* * * * *",
                    timezone="UTC",
                    node_ids=(NODE_ID,),
                ),
            )
        assert published == [
            ("script.scheduled", {"script_id": str(SCRIPT_ID)})
        ]


class TestDockerContainerEvents:
    @pytest.mark.asyncio
    async def test_start_container_publishes_event(self) -> None:
        runner: Any = AsyncMock()
        runner.get_target = AsyncMock(return_value=MagicMock())
        runner.build_command = MagicMock(return_value="docker start abc")
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        broadcaster, published = _broadcaster()
        with patch(
            "app.application.services.sse_broadcaster.get_sse_broadcaster",
            return_value=broadcaster,
        ):
            await svc.start_container(NODE_ID, "abc123")
        assert published == [
            (
                "docker.container.start",
                {"node_id": str(NODE_ID), "container_id": "abc123"},
            )
        ]
