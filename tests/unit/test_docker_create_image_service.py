"""Unit tests for new Docker image/container use cases (mocked command runner)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.dto.docker import (
    ContainerCreateRequestDTO,
    DockerImageBuildRequestDTO,
    DockerImageTagRequestDTO,
)
from app.application.services.docker.bulk_service import DockerBulkService
from app.application.services.docker.container_service import (
    DockerContainerService,
    parse_since,
)
from app.application.services.docker.image_service import (
    DockerImageService,
    _integer,
    _json_object,
    _optional_string,
    _string,
    _string_tuple,
)
from app.core.exceptions import (
    ConnectionFailedError,
    DockerValidationError,
    ImageNotFoundError,
)

NODE = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_node(node_id: str = str(NODE)) -> MagicMock:
    mock_node = MagicMock()
    mock_node.id = uuid.UUID(node_id)
    mock_node.name = "docker-node"
    mock_node.connection_type = "docker"
    mock_node.docker_host = None
    return mock_node


def _make_runner(
    node: MagicMock | None = None,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> AsyncMock:
    runner = AsyncMock()
    runner.get_target = AsyncMock(return_value=node or _make_node())
    runner.get_targets_by_tags = AsyncMock(return_value=[])
    runner.build_command = MagicMock(side_effect=lambda n, args: f"docker {args}")
    runner.execute = AsyncMock(return_value=(stdout, stderr, exit_code))
    return runner


# ---------------------------------------------------------------------------
# Container create
# ---------------------------------------------------------------------------


class TestCreateContainer:
    async def test_success_returns_container_id(self) -> None:
        runner = _make_runner(stdout="abc123def456789\n")
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(
            node_id=NODE,
            image="alpine:latest",
            name="my-ctr",
            command="sleep 60",
            ports=(("80/tcp", "8080"),),
            volumes=(("/host", "/container", "rw"),),
            env=("ENV_VAR=value",),
            labels=(("com.example.foo", "bar"),),
            network="bridge",
            restart_policy="always",
        )
        result = await service.create_container(request)
        assert result.id == "abc123def456789"
        assert result.name == "my-ctr"
        assert result.image == "alpine:latest"
        assert result.status == "created"

        build_args = runner.build_command.call_args[0][1]
        assert build_args.startswith("create ")
        assert "--name my-ctr" in build_args
        assert "--restart always" in build_args
        assert "-p 8080:80/tcp" in build_args
        assert "-v /host:/container:rw" in build_args
        assert "-e ENV_VAR=value" in build_args
        assert "--label com.example.foo=bar" in build_args
        assert "--network bridge" in build_args
        assert "alpine:latest" in build_args
        assert "'sleep 60'" in build_args

    async def test_minimal_request(self) -> None:
        runner = _make_runner(stdout="deadbeef\n")
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(node_id=NODE, image="alpine")
        result = await service.create_container(request)
        assert result.id == "deadbeef"
        assert result.name == "deadbeef"
        build_args = runner.build_command.call_args[0][1]
        assert build_args == "create alpine"

    async def test_invalid_image_raises(self) -> None:
        runner = _make_runner()
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(node_id=NODE, image="alpine; rm -rf /")
        with pytest.raises(DockerValidationError):
            await service.create_container(request)

    async def test_invalid_container_name_raises(self) -> None:
        runner = _make_runner()
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(
            node_id=NODE, image="alpine", name="bad name"
        )
        with pytest.raises(DockerValidationError):
            await service.create_container(request)

    async def test_invalid_restart_policy_raises(self) -> None:
        runner = _make_runner()
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(
            node_id=NODE, image="alpine", restart_policy="always-restart"
        )
        with pytest.raises(DockerValidationError):
            await service.create_container(request)

    async def test_invalid_env_entry_raises(self) -> None:
        runner = _make_runner()
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(
            node_id=NODE, image="alpine", env=("1INVALID=value",)
        )
        with pytest.raises(DockerValidationError):
            await service.create_container(request)

    async def test_no_container_id_output_raises(self) -> None:
        runner = _make_runner(stdout="", stderr="", exit_code=0)
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(node_id=NODE, image="alpine")
        with pytest.raises(DockerValidationError, match="no container id"):
            await service.create_container(request)

    async def test_docker_error_propagates(self) -> None:
        runner = _make_runner(
            stdout="", stderr="Error: No such image: missing", exit_code=1
        )
        service = DockerContainerService(runner)
        request = ContainerCreateRequestDTO(node_id=NODE, image="alpine")
        with pytest.raises(ImageNotFoundError):
            await service.create_container(request)


# ---------------------------------------------------------------------------
# Image inspect / remove / tag
# ---------------------------------------------------------------------------


class TestInspectImage:
    async def test_success(self) -> None:
        inspect_json = (
            '{"Id":"sha256:abc123","RepoTags":["alpine:latest"],'
            '"Size":7333821,"Created":"2026-01-01T00:00:00Z",'
            '"Architecture":"amd64","Os":"linux"}'
        )
        runner = _make_runner(stdout=inspect_json)
        service = DockerImageService(runner)
        result = await service.inspect_image(NODE, "sha256:abc123")
        assert result.id == "sha256:abc123"
        assert result.repo_tags == ("alpine:latest",)
        assert result.size == 7333821
        assert result.architecture == "amd64"
        assert result.os == "linux"
        args = runner.build_command.call_args[0][1]
        assert "inspect --type=image sha256:abc123" in args

    async def test_empty_output_raises(self) -> None:
        runner = _make_runner(stdout="[]")
        service = DockerImageService(runner)
        with pytest.raises(DockerValidationError):
            await service.inspect_image(NODE, "alpine:latest")

    async def test_invalid_image_raises(self) -> None:
        runner = _make_runner()
        service = DockerImageService(runner)
        with pytest.raises(DockerValidationError):
            await service.inspect_image(NODE, "alpine; rm -rf")

    async def test_non_string_fields_use_defaults(self) -> None:
        inspect_json = (
            '{"Id":123,"RepoTags":["a"],'
            '"Size":"big","Created":false,"Architecture":null,"Os":[]}'
        )
        runner = _make_runner(stdout=inspect_json)
        service = DockerImageService(runner)
        result = await service.inspect_image(NODE, "a")
        assert result.id == ""
        assert result.size == 0
        assert result.created == ""
        assert result.architecture == ""
        assert result.os == ""


class TestPullImage:
    async def test_success(self) -> None:
        runner = _make_runner(stdout="Downloaded", stderr="", exit_code=0)
        service = DockerImageService(runner)
        result = await service.pull_image(NODE, "alpine:latest")
        assert result.success is True
        assert result.image == "alpine:latest"

    async def test_connection_failed_returns_failure(self) -> None:
        runner = _make_runner()
        runner.execute = AsyncMock(side_effect=ConnectionFailedError("ssh unreachable"))
        service = DockerImageService(runner)
        result = await service.pull_image(NODE, "alpine:latest")
        assert result.success is False
        assert "ssh unreachable" in result.output


class TestRemoveImage:
    async def test_success(self) -> None:
        runner = _make_runner()
        service = DockerImageService(runner)
        await service.remove_image(NODE, "alpine:latest")
        args = runner.build_command.call_args[0][1]
        assert args == "rmi alpine:latest"

    async def test_not_found_propagates(self) -> None:
        runner = _make_runner(stderr="Error: No such image: x", exit_code=1)
        service = DockerImageService(runner)
        with pytest.raises(ImageNotFoundError):
            await service.remove_image(NODE, "missing:latest")


class TestTagImage:
    async def test_success(self) -> None:
        runner = _make_runner()
        service = DockerImageService(runner)
        result = await service.tag_image(
            DockerImageTagRequestDTO(
                node_id=NODE,
                image_id="alpine:latest",
                repo="my-registry.com/app",
                tag="v1.0",
            )
        )
        assert result.source == "alpine:latest"
        assert result.target == "my-registry.com/app:v1.0"
        args = runner.build_command.call_args[0][1]
        assert "tag alpine:latest my-registry.com/app:v1.0" in args

    async def test_invalid_repo_raises(self) -> None:
        runner = _make_runner()
        service = DockerImageService(runner)
        with pytest.raises(DockerValidationError):
            await service.tag_image(
                DockerImageTagRequestDTO(
                    node_id=NODE, image_id="alpine:latest", repo="bad repo", tag="v1.0"
                )
            )


# ---------------------------------------------------------------------------
# Image build
# ---------------------------------------------------------------------------


class TestBuildImage:
    async def test_success_parses_sha(self) -> None:
        stdout = (
            "Step 1/2: FROM alpine:latest\n"
            "Step 2/2: RUN echo hello\n"
            "Successfully built sha256:abcdef123456\n"
        )
        runner = _make_runner(stdout=stdout)
        service = DockerImageService(runner)
        result = await service.build_image(
            DockerImageBuildRequestDTO(
                node_id=NODE,
                dockerfile="FROM alpine:latest\nRUN echo hello",
                tag="my-image:v1.0",
            )
        )
        assert result.tag == "my-image:v1.0"
        assert result.image_id == "sha256:abcdef123456"
        assert "Successfully built" in result.output

    async def test_success_parses_short_id(self) -> None:
        stdout = "Step 1/1: FROM alpine\nSuccessfully built abc123def456\n"
        runner = _make_runner(stdout=stdout)
        service = DockerImageService(runner)
        result = await service.build_image(
            DockerImageBuildRequestDTO(
                node_id=NODE, dockerfile="FROM alpine", tag="img:1"
            )
        )
        assert result.image_id == "abc123def456"

    async def test_success_parses_sha_from_inline_token(self) -> None:
        stdout = "Step 1/1: FROM alpine\nBuilt intermediate image sha256:inline123\n"
        runner = _make_runner(stdout=stdout)
        service = DockerImageService(runner)
        result = await service.build_image(
            DockerImageBuildRequestDTO(
                node_id=NODE, dockerfile="FROM alpine", tag="img:1"
            )
        )
        assert result.image_id == "sha256:inline123"

    async def test_no_image_id_returns_empty(self) -> None:
        runner = _make_runner(stdout="Step 1/1: FROM alpine\n")
        service = DockerImageService(runner)
        result = await service.build_image(
            DockerImageBuildRequestDTO(
                node_id=NODE, dockerfile="FROM alpine", tag="img:1"
            )
        )
        assert result.image_id == ""

    async def test_build_args_quoted(self) -> None:
        runner = _make_runner(stdout="Successfully built sha256:zzz\n")
        service = DockerImageService(runner)
        await service.build_image(
            DockerImageBuildRequestDTO(
                node_id=NODE,
                dockerfile="FROM alpine",
                tag="img:1",
                build_args=(("VERSION", "1.0"),),
                no_cache=True,
            )
        )
        args = runner.build_command.call_args[0][1]
        assert "--tag img:1" in args
        assert "--build-arg VERSION=1.0" in args
        assert "--no-cache" in args
        assert args.endswith(" -")
        assert "printf %s 'FROM alpine'" in args

    async def test_invalid_tag_raises(self) -> None:
        runner = _make_runner()
        service = DockerImageService(runner)
        with pytest.raises(DockerValidationError):
            await service.build_image(
                DockerImageBuildRequestDTO(
                    node_id=NODE, dockerfile="FROM alpine", tag="bad tag"
                )
            )

    async def test_invalid_build_arg_key_raises(self) -> None:
        runner = _make_runner()
        service = DockerImageService(runner)
        with pytest.raises(DockerValidationError):
            await service.build_image(
                DockerImageBuildRequestDTO(
                    node_id=NODE,
                    dockerfile="FROM alpine",
                    tag="img:1",
                    build_args=(("1BAD", "v"),),
                )
            )


class TestImageHelpers:
    def test_optional_string(self) -> None:
        assert _optional_string("x") == "x"
        assert _optional_string(123) is None

    def test_string(self) -> None:
        assert _string("x") == "x"
        assert _string(123) == ""
        assert _string(None, "default") == "default"

    def test_integer(self) -> None:
        assert _integer(42) == 42
        assert _integer(True) == 0
        assert _integer("42") == 0
        assert _integer(None, 5) == 5

    def test_json_object(self) -> None:
        assert _json_object({"a": 1}) == {"a": 1}
        assert _json_object({1: "a"}) == {"1": "a"}
        assert _json_object("not dict") == {}

    def test_string_tuple(self) -> None:
        assert _string_tuple(["a", "b"]) == ("a", "b")
        assert _string_tuple(["a", 1]) == ("a",)
        assert _string_tuple("not list") == ()


# ---------------------------------------------------------------------------
# Bulk by tags
# ---------------------------------------------------------------------------


def _make_tag_node(node_id: str, name: str = "tag-node") -> MagicMock:
    node = MagicMock()
    node.id = uuid.UUID(node_id)
    node.name = name
    node.connection_type = "docker"
    node.docker_host = None
    return node


# ---------------------------------------------------------------------------
# parse_since — ISO 8601 / Unix timestamp normalization (B.3)
# ---------------------------------------------------------------------------


class TestParseSince:
    def test_unix_timestamp_passes_through(self) -> None:
        assert parse_since("1700000000") == "1700000000"

    def test_iso_8601_with_z_normalizes_to_unix(self) -> None:
        dt = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
        expected = str(int(dt.timestamp()))
        assert parse_since("2026-08-10T12:00:00Z") == expected

    def test_iso_8601_with_offset_normalizes_to_unix(self) -> None:
        dt_utc = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)
        expected = str(int(dt_utc.timestamp()))
        # +03:00 → 09:00 UTC
        assert parse_since("2026-08-10T15:00:00+03:00") == expected

    def test_iso_8601_without_timezone_uses_local(self) -> None:
        dt = datetime(2026, 8, 10, 12, 0, 0)
        expected = str(int(dt.astimezone().timestamp()))
        assert parse_since("2026-08-10T12:00:00") == expected

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(DockerValidationError, match="Invalid 'since'"):
            parse_since("not-a-timestamp")

    def test_empty_raises(self) -> None:
        with pytest.raises(DockerValidationError):
            parse_since("")


class TestGetLogsSince:
    async def test_iso_since_normalized_in_command(self) -> None:
        runner = _make_runner(stdout="log line\n")
        service = DockerContainerService(runner)
        await service.get_logs(NODE, "abc123", since="2026-08-10T12:00:00Z")
        args = runner.build_command.call_args[0][1]
        assert "--since " in args
        assert "2026-08-10T12:00:00Z" not in args  # normalized away

    async def test_unix_since_passed_through(self) -> None:
        runner = _make_runner(stdout="log line\n")
        service = DockerContainerService(runner)
        await service.get_logs(NODE, "abc123", since="1700000000")
        args = runner.build_command.call_args[0][1]
        assert "--since 1700000000" in args

    async def test_invalid_since_raises(self) -> None:
        runner = _make_runner()
        service = DockerContainerService(runner)
        with pytest.raises(DockerValidationError):
            await service.get_logs(NODE, "abc123", since="not-a-ts")


class TestBulkByTags:
    async def test_resolve_node_ids_merges_and_dedupes(self) -> None:
        runner = _make_runner()
        runner.get_targets_by_tags = AsyncMock(
            return_value=[
                _make_tag_node(str(NODE)),
                _make_tag_node("00000000-0000-0000-0000-000000000002"),
            ]
        )
        service = DockerBulkService(runner)
        resolved = await service._resolve_node_ids(
            [str(NODE), "00000000-0000-0000-0000-000000000003"],
            ["zone-a"],
        )
        assert resolved == [
            "00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000003",
            "00000000-0000-0000-0000-000000000002",
        ]

    async def test_resolve_without_tags_returns_node_ids_only(self) -> None:
        runner = _make_runner()
        runner.get_targets_by_tags = AsyncMock(return_value=[])
        service = DockerBulkService(runner)
        resolved = await service._resolve_node_ids(["a", "b"], [])
        assert resolved == ["a", "b"]
        runner.get_targets_by_tags.assert_not_called()

    async def test_bulk_action_uses_tags(self) -> None:
        tag_node = _make_tag_node(str(NODE))
        runner = _make_runner()
        runner.get_targets_by_tags = AsyncMock(return_value=[tag_node])
        service = DockerBulkService(runner)
        result = await service.bulk_container_action(
            node_ids=[],
            container_id="abc123def456",
            action="start",
            node_tags=["zone-a"],
        )
        runner.get_targets_by_tags.assert_awaited_once_with(["zone-a"])
        assert result.total == 1
        assert result.succeeded == 1

    async def test_bulk_exec_with_tags_only(self) -> None:
        tag_node = _make_tag_node(str(NODE))
        runner = _make_runner(stdout="hello")
        runner.get_targets_by_tags = AsyncMock(return_value=[tag_node])
        service = DockerBulkService(runner)
        result = await service.bulk_exec(
            node_ids=[],
            container_id="abc123def456",
            command="echo hello",
            node_tags=["zone-a"],
        )
        assert result.action == "exec"
        assert result.results[0].output == "hello"
