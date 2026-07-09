"""Tests for database models."""

import uuid

from app.models.node import NodeModel


def test_node_model_creation():
    """Test that NodeModel can be created with required fields."""
    node = NodeModel(
        id=uuid.uuid4(),
        name="test-node",
        host="192.168.1.100",
        port=22,
        connection_type="ssh",
        status="active",
    )
    assert node.name == "test-node"
    assert node.host == "192.168.1.100"
    assert node.port == 22
    assert node.connection_type == "ssh"
    assert node.status == "active"
    assert isinstance(node.id, uuid.UUID)
