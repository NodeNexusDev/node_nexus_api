"""Unit tests for DockerContainerService.get_logs stream handling."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

from app.application.services.docker.container_service import DockerContainerService

NODE = uuid.uuid4()
CID = "abc123def456"


def _make_runner(stdout: str = "", stderr: str = "", exit_code: int = 0) -> AsyncMock:
    runner = AsyncMock()
    runner.get_target = AsyncMock(return_value=MagicMock())
    runner.build_command = MagicMock(side_effect=lambda n, args: f"docker {args}")
    runner.execute = AsyncMock(return_value=(stdout, stderr, exit_code))
    return runner


class TestGetLogsStreams:
    async def test_stdout_only_unchanged(self) -> None:
        service = DockerContainerService(_make_runner(stdout="line1\nline2\n"))
        assert await service.get_logs(NODE, CID) == "line1\nline2\n"

    async def test_stderr_only_is_returned(self) -> None:
        # Regression: containers logging to stderr had their logs dropped.
        service = DockerContainerService(_make_runner(stdout="", stderr="oops\n"))
        assert await service.get_logs(NODE, CID) == "oops\n"

    async def test_both_streams_concatenated(self) -> None:
        service = DockerContainerService(
            _make_runner(stdout="out\n", stderr="err\n")
        )
        assert await service.get_logs(NODE, CID) == "out\nerr\n"

    async def test_both_empty(self) -> None:
        service = DockerContainerService(_make_runner())
        assert await service.get_logs(NODE, CID) == ""
