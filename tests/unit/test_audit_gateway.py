"""Unit tests for audit persistence adapter mappings."""

from datetime import UTC, datetime
from uuid import uuid4

from app.adapters.persistence.audit import (
    SqlAlchemyAuditLogGateway,
    _outbox_model,
)
from app.application.dto.audit import AuditEventDTO
from app.models.audit_log import AuditLogModel


def test_maps_audit_log_to_application_dto() -> None:
    model = AuditLogModel(
        id=uuid4(),
        node_id=None,
        action="execute",
        user="operator",
        details='{"result": "ok"}',
        created_at=datetime.now(UTC),
    )

    dto = SqlAlchemyAuditLogGateway._to_dto(model)

    assert dto.id == model.id
    assert dto.action == "execute"
    assert dto.details == '{"result": "ok"}'


def test_maps_safe_event_to_outbox_payload() -> None:
    node_id = uuid4()
    model = _outbox_model(
        AuditEventDTO(
            action="execute",
            node_id=node_id,
            details={"result": "ok"},
        )
    )

    assert model.payload["node_id"] == str(node_id)
    assert model.payload["action"] == "execute"
    assert "result" in model.payload["details"]
