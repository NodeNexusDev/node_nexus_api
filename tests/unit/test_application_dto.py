"""Tests for internal application DTOs and persistence mappings."""

import uuid

import pytest

from app.application.dto.command_execution import CommandRequestDTO, CommandResultDTO
from app.application.dto.node_connection import NodeConnectionDTO
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
