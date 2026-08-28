"""Tests for immutable Docker application contracts."""

import uuid

import pytest

from app.application.dto.docker import (
    BulkDockerNodeResultDTO,
    BulkDockerRequestDTO,
    BulkDockerResultDTO,
    DockerContainerDTO,
    DockerExecRequestDTO,
)


def test_container_view_is_immutable() -> None:
    container = DockerContainerDTO(
        id="abc",
        names="web",
        image="nginx",
        command="nginx",
        created_at="now",
        state="running",
        status="Up",
    )
    with pytest.raises(AttributeError):
        setattr(container, "state", "stopped")


def test_exec_request_keeps_typed_node_identifier() -> None:
    node_id = uuid.uuid4()
    request = DockerExecRequestDTO(
        node_id=node_id,
        container_id="web",
        command="id",
    )
    assert request.node_id == node_id
    assert request.timeout == 30


def test_bulk_contracts_use_immutable_collections() -> None:
    node_id = uuid.uuid4()
    request = BulkDockerRequestDTO(
        node_ids=(node_id,),
        container_id="web",
        action="restart",
    )
    result = BulkDockerResultDTO(
        action=request.action,
        results=(
            BulkDockerNodeResultDTO(
                node_id=str(node_id),
                node_name="node",
                status="success",
            ),
        ),
        total=1,
        succeeded=1,
        failed=0,
    )
    assert request.node_ids == (node_id,)
    assert result.results[0].node_id == str(node_id)
