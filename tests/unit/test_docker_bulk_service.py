"""Unit tests for DockerBulkService methods."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.services.docker.bulk_service import DockerBulkService
from app.core.exceptions import DockerError


def _make_node(
    node_id: uuid.UUID | None = None,
    name: str = "server1",
    connection_type: str = "docker",
) -> NodeConnectionDTO:
    return NodeConnectionDTO(
        id=node_id or uuid.uuid4(),
        name=name,
        host="10.0.0.1",
        port=22,
        connection_type=connection_type,
        username="root",
        password="enc",
        ssh_key="enc",
        passphrase=None,
    )


def _make_runner() -> AsyncMock:
    runner = AsyncMock()
    runner.build_command = MagicMock(return_value="ssh root@10.0.0.1 docker ...")
    return runner


# ── _prepare: ValueError / DockerError branch ──


@pytest.mark.asyncio
async def test_prepare_docker_error() -> None:
    runner = _make_runner()
    node_id = uuid.uuid4()
    runner.get_target = AsyncMock(side_effect=DockerError("connection refused"))
    service = DockerBulkService(runner)

    prepared, slots = await service._prepare([node_id])

    assert prepared == []
    assert slots[0].status == "error"
    assert "connection refused" in slots[0].error


@pytest.mark.asyncio
async def test_prepare_value_error() -> None:
    runner = _make_runner()
    node_id = uuid.uuid4()
    runner.get_target = AsyncMock(side_effect=ValueError("bad host"))
    service = DockerBulkService(runner)

    prepared, slots = await service._prepare([node_id])

    assert prepared == []
    assert slots[0].status == "error"
    assert "bad host" in slots[0].error


# ── _resolve_node_ids: tag exception branch ──


@pytest.mark.asyncio
async def test_resolve_node_ids_tag_exception() -> None:
    runner = _make_runner()
    runner.get_targets_by_tags = AsyncMock(side_effect=RuntimeError("db down"))
    service = DockerBulkService(runner)

    node_id = uuid.uuid4()
    result = await service._resolve_node_ids([node_id], ["prod"])

    assert result == [node_id]


# ── bulk_container_action: remove action ──


@pytest.mark.asyncio
async def test_bulk_container_action_remove() -> None:
    runner = _make_runner()
    node = _make_node()
    node_id = node.id
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("removed", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_container_action(
        node_ids=[node_id],
        container_id="abc123def456",
        action="remove",
    )

    assert result.succeeded == 1
    assert result.failed == 0
    cmd_args = runner.build_command.call_args[0][1]
    assert "rm -f" in cmd_args


# ── bulk_pull_image ──


@pytest.mark.asyncio
async def test_bulk_pull_image_all_success() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("Pull complete", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_pull_image(node_ids=[node.id], image="nginx:latest")

    assert result.total == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert result.results[0].output == "Pull complete"


@pytest.mark.asyncio
async def test_bulk_pull_image_one_fails() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("", "not found", 1))
    service = DockerBulkService(runner)

    result = await service.bulk_pull_image(node_ids=[node.id], image="nonexistent:tag")

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 1
    assert "not found" in result.results[0].error


@pytest.mark.asyncio
async def test_bulk_pull_image_exception() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(side_effect=RuntimeError("ssh timeout"))
    service = DockerBulkService(runner)

    result = await service.bulk_pull_image(node_ids=[node.id], image="nginx:latest")

    assert result.total == 1
    assert result.failed == 1
    assert "ssh timeout" in result.results[0].error


# ── bulk_image_remove ──


@pytest.mark.asyncio
async def test_bulk_image_remove_all_success() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("Untagged: nginx", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_image_remove(
        node_ids=[node.id], image_id="nginx:latest"
    )

    assert result.total == 1
    assert result.succeeded == 1
    cmd_args = runner.build_command.call_args[0][1]
    assert "rmi -f" in cmd_args


@pytest.mark.asyncio
async def test_bulk_image_remove_one_fails() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("", "image not found", 1))
    service = DockerBulkService(runner)

    result = await service.bulk_image_remove(node_ids=[node.id], image_id="nonexistent")

    assert result.total == 1
    assert result.failed == 1
    assert "image not found" in result.results[0].error


@pytest.mark.asyncio
async def test_bulk_image_remove_exception() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
    service = DockerBulkService(runner)

    result = await service.bulk_image_remove(
        node_ids=[node.id], image_id="nginx:latest"
    )

    assert result.total == 1
    assert result.failed == 1
    assert "connection lost" in result.results[0].error


# ── bulk_image_build ──


@pytest.mark.asyncio
async def test_bulk_image_build_no_args() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("Successfully built abc123", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_image_build(
        node_ids=[node.id],
        dockerfile="FROM ubuntu",
        tag="myapp:latest",
    )

    assert result.total == 1
    assert result.succeeded == 1
    cmd_args = runner.build_command.call_args[0][1]
    assert "-t myapp:latest" in cmd_args
    assert "--no-cache" not in cmd_args
    assert "--build-arg" not in cmd_args


@pytest.mark.asyncio
async def test_bulk_image_build_with_args() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("Successfully built abc123", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_image_build(
        node_ids=[node.id],
        dockerfile="FROM ubuntu",
        tag="myapp:latest",
        build_args={"PYTHON_VERSION": "3.12", "DEBUG": "true"},
        no_cache=True,
    )

    assert result.succeeded == 1
    cmd_args = runner.build_command.call_args[0][1]
    assert "--no-cache" in cmd_args
    assert "--build-arg PYTHON_VERSION=3.12" in cmd_args
    assert "--build-arg DEBUG=true" in cmd_args


@pytest.mark.asyncio
async def test_bulk_image_build_exception() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(side_effect=RuntimeError("docker daemon down"))
    service = DockerBulkService(runner)

    result = await service.bulk_image_build(
        node_ids=[node.id],
        dockerfile="FROM ubuntu",
        tag="myapp:latest",
    )

    assert result.total == 1
    assert result.failed == 1
    assert "docker daemon down" in result.results[0].error


# -- bulk_inspect --


@pytest.mark.asyncio
async def test_bulk_inspect_success() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=('[{"Id":"abc123"}]', "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_inspect(
        node_ids=[node.id],
        container_id="abc123def456",
    )

    assert result.total == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert "abc123" in result.results[0].output


@pytest.mark.asyncio
async def test_bulk_inspect_error() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("", "Error: no such container", 1))
    service = DockerBulkService(runner)

    result = await service.bulk_inspect(
        node_ids=[node.id],
        container_id="nonexistent",
    )

    assert result.total == 1
    assert result.failed == 1
    assert "no such container" in result.results[0].error


@pytest.mark.asyncio
async def test_bulk_inspect_exception() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(side_effect=RuntimeError("ssh timeout"))
    service = DockerBulkService(runner)

    result = await service.bulk_inspect(
        node_ids=[node.id],
        container_id="abc123def456",
    )

    assert result.total == 1
    assert result.failed == 1
    assert "ssh timeout" in result.results[0].error


# -- bulk_logs --


@pytest.mark.asyncio
async def test_bulk_logs_success() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("log line 1\nlog line 2\n", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_logs(
        node_ids=[node.id],
        container_id="abc123def456",
    )

    assert result.total == 1
    assert result.succeeded == 1
    assert "log line 1" in result.results[0].output


@pytest.mark.asyncio
async def test_bulk_logs_custom_tail() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("logs\n", "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_logs(
        node_ids=[node.id],
        container_id="abc123def456",
        tail=50,
    )

    assert result.succeeded == 1
    cmd_args = runner.build_command.call_args[0][1]
    assert "--tail 50" in cmd_args


@pytest.mark.asyncio
async def test_bulk_logs_error() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("", "Error: no such container", 1))
    service = DockerBulkService(runner)

    result = await service.bulk_logs(
        node_ids=[node.id],
        container_id="nonexistent",
    )

    assert result.total == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_bulk_logs_exception() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(side_effect=RuntimeError("connection lost"))
    service = DockerBulkService(runner)

    result = await service.bulk_logs(
        node_ids=[node.id],
        container_id="abc123def456",
    )

    assert result.total == 1
    assert result.failed == 1
    assert "connection lost" in result.results[0].error


# -- bulk_stats --


@pytest.mark.asyncio
async def test_bulk_stats_success() -> None:
    stats_json = (
        '{"Container":"abc123","Name":"web","CPUPerc":"0.5%",'
        '"MemUsage":"100MiB","MemPerc":"1.0%","NetIO":"1MB/2MB",'
        '"BlockIO":"10MB/20MB"}'
    )
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=(stats_json, "", 0))
    service = DockerBulkService(runner)

    result = await service.bulk_stats(
        node_ids=[node.id],
        container_id="abc123def456",
    )

    assert result.total == 1
    assert result.succeeded == 1
    assert "abc123" in result.results[0].output


@pytest.mark.asyncio
async def test_bulk_stats_error() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(return_value=("", "Error: not running", 1))
    service = DockerBulkService(runner)

    result = await service.bulk_stats(
        node_ids=[node.id],
        container_id="nonexistent",
    )

    assert result.total == 1
    assert result.failed == 1
    assert "not running" in result.results[0].error


@pytest.mark.asyncio
async def test_bulk_stats_exception() -> None:
    runner = _make_runner()
    node = _make_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.execute = AsyncMock(side_effect=RuntimeError("ssh timeout"))
    service = DockerBulkService(runner)

    result = await service.bulk_stats(
        node_ids=[node.id],
        container_id="abc123def456",
    )

    assert result.total == 1
    assert result.failed == 1
    assert "ssh timeout" in result.results[0].error
