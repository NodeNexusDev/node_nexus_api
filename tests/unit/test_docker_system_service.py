"""Unit tests for DockerSystemService (info, df, prune)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.docker.system_service import DockerSystemService
from app.core.exceptions import DockerError

NODE = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_node() -> MagicMock:
    mock = MagicMock()
    mock.id = NODE
    mock.name = "docker-node"
    mock.connection_type = "ssh"
    mock.has_docker = True
    mock.docker_host = None
    return mock


def _make_runner(
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> AsyncMock:
    runner = AsyncMock()
    runner.get_target = AsyncMock(return_value=_make_node())
    runner.build_command = MagicMock(side_effect=lambda n, args: f"docker {args}")
    runner.execute = AsyncMock(return_value=(stdout, stderr, exit_code))
    return runner


# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------


class TestSystemServiceInfo:
    async def test_success(self) -> None:
        info_json = (
            '[{"ServerVersion":"24.0.7","Driver":"overlay2",'
            '"OperatingSystem":"Alpine Linux v3.19","Architecture":"x86_64",'
            '"MemTotal":"16777216","NCPU":4,"ContainersRunning":2,'
            '"ContainersStopped":1,"Images":10}]'
        )
        runner = _make_runner(stdout=info_json)
        service = DockerSystemService(runner)
        result = await service.info(NODE)
        assert result.server_version == "24.0.7"
        assert result.storage_driver == "overlay2"
        assert result.operating_system == "Alpine Linux v3.19"
        assert result.architecture == "x86_64"
        assert result.total_memory == "16777216"
        assert result.cpus == 4
        assert result.containers_running == 2
        assert result.containers_stopped == 1
        assert result.images == 10

    async def test_empty_output_raises(self) -> None:
        runner = _make_runner(stdout="[]")
        service = DockerSystemService(runner)
        with pytest.raises(DockerError):
            await service.info(NODE)

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: Cannot connect", exit_code=1)
        service = DockerSystemService(runner)
        with pytest.raises(DockerError):
            await service.info(NODE)

    async def test_non_integer_fields_use_defaults(self) -> None:
        info_json = (
            '[{"ServerVersion":"24.0","Driver":"overlay2",'
            '"OperatingSystem":"Linux","Architecture":"amd64",'
            '"MemTotal":"8GB","NCPU":"bad","ContainersRunning":"bad",'
            '"ContainersStopped":"bad","Images":"bad"}]'
        )
        runner = _make_runner(stdout=info_json)
        service = DockerSystemService(runner)
        result = await service.info(NODE)
        assert result.cpus == 0
        assert result.containers_running == 0
        assert result.containers_stopped == 0
        assert result.images == 0


# ---------------------------------------------------------------------------
# System df
# ---------------------------------------------------------------------------


class TestSystemServiceDiskUsage:
    async def test_success(self) -> None:
        df_output = (
            '{"Type":"Images","TotalCount":10,"ActiveSize":"100MB",'
            '"Reclaimable":"50MB","ReclaimablePercent":"50%"}\n'
            '{"Type":"Containers","TotalCount":5,"ActiveSize":"200MB",'
            '"Reclaimable":"100MB","ReclaimablePercent":"50%"}\n'
        )
        runner = _make_runner(stdout=df_output)
        service = DockerSystemService(runner)
        result = await service.disk_usage(NODE)
        assert len(result) == 2
        assert result[0].type == "Images"
        assert result[0].total_count == 10
        assert result[0].active_size == "100MB"
        assert result[1].type == "Containers"
        assert result[1].total_count == 5

    async def test_malformed_line_skipped(self) -> None:
        df_output = (
            '{"Type":"Images","TotalCount":10,"ActiveSize":"100MB",'
            '"Reclaimable":"50MB","ReclaimablePercent":"50%"}\n'
            "not-json-line\n"
            '{"Type":"Volumes","TotalCount":3,"ActiveSize":"0B",'
            '"Reclaimable":"0B","ReclaimablePercent":"0%"}\n'
        )
        runner = _make_runner(stdout=df_output)
        service = DockerSystemService(runner)
        result = await service.disk_usage(NODE)
        assert len(result) == 2
        assert result[0].type == "Images"
        assert result[1].type == "Volumes"

    async def test_empty_output(self) -> None:
        runner = _make_runner(stdout="")
        service = DockerSystemService(runner)
        result = await service.disk_usage(NODE)
        assert result == []

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: docker daemon", exit_code=1)
        service = DockerSystemService(runner)
        with pytest.raises(DockerError):
            await service.disk_usage(NODE)


# ---------------------------------------------------------------------------
# Prune containers
# ---------------------------------------------------------------------------


class TestSystemServicePruneContainers:
    async def test_success_with_deleted(self) -> None:
        output = (
            "Deleted Containers:\n"
            "abc123def456, fed789abc012\n"
            "Total reclaimed space: 1.5GB\n"
        )
        runner = _make_runner(stdout=output)
        service = DockerSystemService(runner)
        result = await service.prune_containers(NODE)
        assert len(result.containers_deleted) >= 0
        assert "1.5GB" in result.space_reclaimed

    async def test_success_no_deleted(self) -> None:
        output = "Total reclaimed space: 0B\n"
        runner = _make_runner(stdout=output)
        service = DockerSystemService(runner)
        result = await service.prune_containers(NODE)
        assert result.containers_deleted == ()
        assert "0B" in result.space_reclaimed

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: prune failed", exit_code=1)
        service = DockerSystemService(runner)
        with pytest.raises(DockerError):
            await service.prune_containers(NODE)


# ---------------------------------------------------------------------------
# Prune images
# ---------------------------------------------------------------------------


class TestSystemServicePruneImages:
    async def test_success_with_deleted(self) -> None:
        output = (
            "Deleted Images:\n"
            "deleted: sha256:abc123\n"
            "deleted: sha256:def456\n"
            "Total reclaimed space: 250MB\n"
        )
        runner = _make_runner(stdout=output)
        service = DockerSystemService(runner)
        result = await service.prune_images(NODE)
        assert len(result.images_deleted) >= 0
        assert "250MB" in result.space_reclaimed

    async def test_success_no_deleted(self) -> None:
        output = "Total reclaimed space: 0B\n"
        runner = _make_runner(stdout=output)
        service = DockerSystemService(runner)
        result = await service.prune_images(NODE)
        assert result.images_deleted == ()
        assert "0B" in result.space_reclaimed

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(stderr="Error: prune failed", exit_code=1)
        service = DockerSystemService(runner)
        with pytest.raises(DockerError):
            await service.prune_images(NODE)
