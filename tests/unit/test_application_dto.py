"""Tests for internal application DTOs and persistence mappings."""

import uuid

import pytest

from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    BulkCommandResultDTO,
    CommandExecutionDTO,
    CommandRequestDTO,
    CommandResultDTO,
)
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.node_metrics import (
    CpuMetricsDTO,
    NodeMetricsDTO,
    UsageMetricsDTO,
)
from app.application.ports.node_reader import NodeConnectionReader
from app.models.node import NodeModel
from app.repositories.node_repo import NodeRepository


def test_node_connection_dto_hides_secrets_from_repr() -> None:
    dto = NodeConnectionDTO(
        id=uuid.uuid4(),
        name="node",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
        username="root",
        password="plain-password",
        ssh_key="private-key",
    )

    representation = repr(dto)

    assert "plain-password" not in representation
    assert "private-key" not in representation


def test_command_boundary_dtos_are_immutable() -> None:
    request = CommandRequestDTO(command="uptime", timeout=30)
    result = CommandResultDTO(stdout="ok", stderr="", exit_code=0)

    assert request.command == "uptime"
    assert result.exit_code == 0
    with pytest.raises(AttributeError):
        request.command = "whoami"  # type: ignore[misc]


def test_bulk_command_dtos_use_immutable_collections() -> None:
    node_id = uuid.uuid4()
    request = BulkCommandRequestDTO(
        command="uptime",
        node_ids=(node_id,),
        tags=("prod",),
    )
    result = BulkCommandResultDTO(
        command="uptime",
        results=(
            CommandExecutionDTO(
                node_id=node_id,
                node_name="node",
                stdout="ok",
                stderr="",
                exit_code=0,
            ),
        ),
        total=1,
        succeeded=1,
        failed=0,
    )

    assert request.node_ids == (node_id,)
    assert result.results[0].node_id == node_id


def test_node_metrics_dto_is_immutable() -> None:
    metrics = NodeMetricsDTO(
        cpu=CpuMetricsDTO(usage_percent=25.0, cores=4),
        memory=UsageMetricsDTO(total_bytes=100, used_bytes=50, percent=50.0),
        disk=UsageMetricsDTO(total_bytes=200, used_bytes=100, percent=50.0),
        uptime_since="2026-07-29 10:00:00",
    )

    assert metrics.cpu.cores == 4
    with pytest.raises(AttributeError):
        metrics.uptime_since = "changed"  # type: ignore[misc]


def test_node_repository_maps_connection_dto() -> None:
    node = NodeModel(
        id=uuid.uuid4(),
        name="node",
        host="10.0.0.1",
        port=2222,
        connection_type="docker",
        username="operator",
        password="encrypted-password",
        ssh_key="encrypted-key",
        docker_host="tcp://docker:2375",
        tags=[],
    )

    dto = NodeRepository._to_connection_dto(node)

    assert dto.id == node.id
    assert dto.name == "node"
    assert dto.host == "10.0.0.1"
    assert dto.port == 2222
    assert dto.connection_type == "docker"
    assert dto.username == "operator"
    assert dto.password == "encrypted-password"
    assert dto.ssh_key == "encrypted-key"
    assert dto.docker_host == "tcp://docker:2375"


def test_node_repository_satisfies_reader_protocol() -> None:
    assert isinstance(NodeRepository, type)
    reader: type[NodeConnectionReader] = NodeRepository
    assert reader is NodeRepository
