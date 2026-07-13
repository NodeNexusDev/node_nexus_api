"""Tests for AuditLogModel."""

import uuid

from app.models.audit_log import AuditLogModel


def test_audit_log_model_creation():
    """Test that AuditLogModel can be created with required fields."""
    log = AuditLogModel(
        id=uuid.uuid4(),
        action="create",
    )
    assert log.action == "create"
    assert log.node_id is None
    assert log.user is None
    assert log.details is None
    assert isinstance(log.id, uuid.UUID)


def test_audit_log_model_with_node_id():
    """Test AuditLogModel with a node_id foreign key."""
    node_id = uuid.uuid4()
    log = AuditLogModel(
        id=uuid.uuid4(),
        node_id=node_id,
        action="update",
        user="admin",
        details='{"name": "test"}',
    )
    assert log.node_id == node_id
    assert log.action == "update"
    assert log.user == "admin"
    assert log.details == '{"name": "test"}'


def test_audit_log_model_nullable_fields():
    """Test that optional fields can be None."""
    log = AuditLogModel(
        id=uuid.uuid4(),
        action="delete",
        node_id=None,
        user=None,
        details=None,
    )
    assert log.node_id is None
    assert log.user is None
    assert log.details is None
