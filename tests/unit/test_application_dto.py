"""Tests for internal application DTOs and persistence mappings."""

import uuid
from datetime import UTC, datetime

import pytest

from app.adapters.persistence.dao.node import NodeRepository
from app.application.dto.command_execution import (
    BulkCommandRequestDTO,
    BulkCommandResultDTO,
    CommandExecutionDTO,
    CommandRequestDTO,
    CommandResultDTO,
)
from app.application.dto.command_management import (
    CommandCreateDTO,
    CommandUpdateDTO,
)
from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.node_management import NodeCreateDTO, NodeUpdateDTO
from app.application.dto.node_metrics import (
    CpuMetricsDTO,
    LoadAverageDTO,
    NodeMetricsDTO,
    UsageMetricsDTO,
)
from app.application.dto.node_view import NodeViewDTO
from app.application.ports.node_reader import NodeConnectionReader
from app.models.node import NodeModel


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
        passphrase="key-passphrase",
    )

    representation = repr(dto)

    assert "plain-password" not in representation
    assert "private-key" not in representation
    assert "key-passphrase" not in representation


def test_node_create_dto_is_immutable_and_hides_secrets() -> None:
    dto = NodeCreateDTO(
        name="node",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
        password="plain-password",
        ssh_key="private-key",
        passphrase="key-passphrase",
    )

    assert "plain-password" not in repr(dto)
    assert "private-key" not in repr(dto)
    assert "key-passphrase" not in repr(dto)
    with pytest.raises(AttributeError):
        dto.name = "changed"  # type: ignore[misc]


def test_node_update_dto_preserves_explicit_null() -> None:
    dto = NodeUpdateDTO(changes=(("username", None),))

    assert dict(dto.changes) == {"username": None}


def test_node_update_dto_hides_sensitive_changes_from_repr() -> None:
    dto = NodeUpdateDTO(changes=(("password", "plain-password"),))

    assert "plain-password" not in repr(dto)


def test_command_boundary_dtos_are_immutable() -> None:
    request = CommandRequestDTO(command="uptime", timeout=30)
    result = CommandResultDTO(stdout="ok", stderr="", exit_code=0)

    assert request.command == "uptime"
    assert result.exit_code == 0
    with pytest.raises(AttributeError):
        request.command = "whoami"  # type: ignore[misc]


def test_command_management_dtos_are_immutable_and_preserve_null() -> None:
    create = CommandCreateDTO(name="uptime", command="uptime", tags=("ops",))
    update = CommandUpdateDTO(changes=(("description", None),))

    assert create.tags == ("ops",)
    assert dict(update.changes) == {"description": None}
    with pytest.raises(AttributeError):
        create.name = "changed"  # type: ignore[misc]


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
        load_average=LoadAverageDTO(one_min=0.5, five_min=0.3, fifteen_min=0.1),
        uptime_since="2026-07-29 10:00:00",
    )

    assert metrics.cpu.cores == 4
    assert metrics.load_average.one_min == 0.5
    with pytest.raises(AttributeError):
        metrics.uptime_since = "changed"  # type: ignore[misc]


def test_node_view_dto_excludes_credentials() -> None:
    node = NodeViewDTO(
        id=uuid.uuid4(),
        name="node",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
        status="active",
        username="root",
        docker_host=None,
        tags=("prod",),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert node.tags == ("prod",)
    assert not hasattr(node, "password")
    assert not hasattr(node, "ssh_key")


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
        passphrase="encrypted-passphrase",
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
    assert dto.passphrase == "encrypted-passphrase"
    assert dto.docker_host == "tcp://docker:2375"


def test_node_repository_satisfies_reader_protocol() -> None:
    assert isinstance(NodeRepository, type)
    reader: type[NodeConnectionReader] = NodeRepository
    assert reader is NodeRepository
