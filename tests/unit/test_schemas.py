"""Tests for Pydantic schema validation."""

import pytest
from pydantic import ValidationError

from app.schemas.node import (
    CommandRequest,
    NodeCreate,
    NodeUpdate,
)


class TestNodeCreate:
    def test_valid(self) -> None:
        node = NodeCreate(
            name="test-node",
            host="192.168.1.100",
            port=22,
            connection_type="ssh",
        )
        assert node.name == "test-node"
        assert node.port == 22

    def test_valid_connection_types(self) -> None:
        for ct in ("ssh", "docker", "proxmox"):
            node = NodeCreate(name="n", host="h", connection_type=ct)
            assert node.connection_type == ct

    def test_invalid_connection_type(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="n", host="h", connection_type="invalid")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="", host="h", connection_type="ssh")

    def test_empty_host_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="n", host="", connection_type="ssh")

    def test_port_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="n", host="h", connection_type="ssh", port=0)

    def test_port_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="n", host="h", connection_type="ssh", port=-1)

    def test_port_too_large_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeCreate(name="n", host="h", connection_type="ssh", port=99999)

    def test_port_max_valid(self) -> None:
        node = NodeCreate(name="n", host="h", connection_type="ssh", port=65535)
        assert node.port == 65535


class TestNodeUpdate:
    def test_valid(self) -> None:
        update = NodeUpdate(name="updated")
        assert update.name == "updated"
        assert update.host is None

    def test_invalid_connection_type(self) -> None:
        with pytest.raises(ValidationError):
            NodeUpdate(connection_type="nope")

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            NodeUpdate(status="invalid")

    def test_valid_status(self) -> None:
        for s in ("active", "unreachable", "error"):
            update = NodeUpdate(status=s)
            assert update.status == s

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            NodeUpdate(name="")

    def test_port_range_validation(self) -> None:
        with pytest.raises(ValidationError):
            NodeUpdate(port=0)
        with pytest.raises(ValidationError):
            NodeUpdate(port=99999)


class TestCommandRequest:
    def test_valid(self) -> None:
        req = CommandRequest(command="uptime")
        assert req.command == "uptime"

    def test_empty_command_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandRequest(command="")

    def test_too_long_command_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CommandRequest(command="x" * 4097)

    def test_max_length_valid(self) -> None:
        req = CommandRequest(command="x" * 4096)
        assert len(req.command) == 4096
