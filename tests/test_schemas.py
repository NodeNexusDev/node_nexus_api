"""Tests for Pydantic schemas."""

import uuid
from datetime import UTC, datetime

from app.schemas.node import NodeCreate, NodeResponse, NodeUpdate


def test_node_create_schema():
    """Test NodeCreate schema validation."""
    data = {"name": "test-node", "host": "192.168.1.100", "connection_type": "ssh"}
    node = NodeCreate(**data)
    assert node.name == "test-node"
    assert node.host == "192.168.1.100"
    assert node.port == 22


def test_node_update_schema():
    """Test NodeUpdate schema validation."""
    data = {"name": "updated-node"}
    node = NodeUpdate(**data)
    assert node.name == "updated-node"
    assert node.host is None


def test_node_response_schema():
    """Test NodeResponse schema from model dict."""
    data = {
        "id": uuid.uuid4(),
        "name": "test-node",
        "host": "192.168.1.100",
        "port": 22,
        "connection_type": "ssh",
        "status": "active",
        "username": "testuser",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    node = NodeResponse(**data)
    assert node.name == "test-node"
