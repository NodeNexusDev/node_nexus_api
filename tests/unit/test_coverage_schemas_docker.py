"""Coverage – schemas (docker, node, common cursor)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.common import decode_cursor, encode_cursor
from app.schemas.docker import (
    BulkDockerImageBuildRequest,
    BulkDockerImageRemoveRequest,
    BulkDockerPullRequest,
    BulkDockerRequest,
)
from app.schemas.node import BulkCommandRequest, NodeCreate, NodeUpdate


class TestCommonCursor:
    def test_encode_naive_datetime(self) -> None:
        # line 95: else branch
        dt = datetime(2026, 1, 15, 10, 30, 0)  # naive
        nid = uuid.uuid4()
        enc = encode_cursor(dt, nid)
        dec_dt, dec_id = decode_cursor(enc)
        assert dec_id == nid
        # decoded should be aware UTC
        assert dec_dt.tzinfo is not None

    def test_encode_aware_datetime(self) -> None:
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        nid = uuid.uuid4()
        enc = encode_cursor(dt, nid)
        dec_dt, dec_id = decode_cursor(enc)
        assert dec_id == nid


class TestDockerSchemas:
    def test_bulk_docker_request_requires_targets(self) -> None:
        with pytest.raises(ValidationError, match="At least one"):
            BulkDockerRequest(node_ids=[], node_tags=[], container_id="abc")
        # valid with node_ids
        r = BulkDockerRequest(node_ids=[uuid.uuid4()], node_tags=[], container_id="abc")
        assert r.container_id == "abc"
        # valid with tags
        r2 = BulkDockerRequest(node_ids=[], node_tags=["prod"], container_id="abc")
        assert r2.node_tags == ["prod"]

    def test_bulk_pull_requires_targets(self) -> None:
        with pytest.raises(ValidationError, match="At least one"):
            BulkDockerPullRequest(node_ids=[], node_tags=[], image="my:tag")
        r = BulkDockerPullRequest(node_ids=[uuid.uuid4()], image="my:tag")
        assert r.image == "my:tag"

    def test_bulk_remove_requires_targets(self) -> None:
        with pytest.raises(ValidationError, match="At least one"):
            BulkDockerImageRemoveRequest(node_ids=[], node_tags=[], image_id="img")
        r = BulkDockerImageRemoveRequest(node_ids=[uuid.uuid4()], image_id="img")
        assert r.image_id == "img"

    def test_bulk_build_requires_targets(self) -> None:
        with pytest.raises(ValidationError, match="At least one"):
            BulkDockerImageBuildRequest(
                node_ids=[], node_tags=[], dockerfile="FROM scratch", tag="my:tag"
            )
        r = BulkDockerImageBuildRequest(
            node_ids=[uuid.uuid4()], dockerfile="FROM scratch", tag="my:tag"
        )
        assert r.tag == "my:tag"


class TestNodeSchemasCoverage:
    def test_node_create_docker_host_without_has_docker(self) -> None:
        with pytest.raises(ValidationError, match="has_docker"):
            NodeCreate(
                name="n", host="h", docker_host="tcp://host:2375", has_docker=False
            )

    def test_node_create_docker_host_invalid(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="n", host="h", docker_host="not-a-valid", has_docker=True)

    def test_node_create_docker_host_valid(self) -> None:
        n = NodeCreate(
            name="n", host="h", docker_host="tcp://host:2375", has_docker=True
        )
        assert n.docker_host == "tcp://host:2375"

    def test_node_update_docker_host_without_has_docker(self) -> None:
        with pytest.raises(ValidationError, match="has_docker"):
            NodeUpdate(docker_host="tcp://host:2375", has_docker=False)

    def test_node_update_docker_host_invalid(self) -> None:
        with pytest.raises(ValidationError):
            NodeUpdate(docker_host="bad::host", has_docker=True)

    def test_node_update_docker_host_valid(self) -> None:
        u = NodeUpdate(docker_host="tcp://host:2375", has_docker=True)
        assert u.docker_host == "tcp://host:2375"

    def test_bulk_command_requires_targets(self) -> None:
        with pytest.raises(ValidationError, match="At least one"):
            BulkCommandRequest(command="echo hi", node_ids=None, tags=None)
        # empty list triggers Field min_length, not validator
        with pytest.raises(ValidationError):
            BulkCommandRequest(command="echo hi", node_ids=[], tags=[])
        # valid
        r = BulkCommandRequest(command="echo hi", node_ids=[uuid.uuid4()], tags=None)
        assert r.command == "echo hi"
        r2 = BulkCommandRequest(command="echo hi", node_ids=None, tags=["prod"])
        assert r2.tags == ["prod"]
