"""Unit tests for audit persistence adapter mappings."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy.engine import CursorResult

from app.adapters.persistence.audit import (
    RequestAuditOutbox,
    RequiredAuditOutbox,
    SqlAlchemyAuditLogGateway,
    _outbox_model,
)
from app.application.dto.audit import AuditEventDTO, AuditLogQueryDTO
from app.models.audit_log import AuditLogModel
from tests.typing import as_typed


class _Context:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


class _Sessionmaker:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def __call__(self) -> _Context:
        return _Context(self._session)

    def begin(self) -> _Context:
        return _Context(self._session)


def _log() -> AuditLogModel:
    return AuditLogModel(
        id=uuid4(),
        node_id=uuid4(),
        action="execute",
        user="operator",
        details='{"result": "ok"}',
        created_at=datetime.now(UTC),
    )


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
    details = model.payload["details"]
    assert isinstance(details, str)
    assert "result" in details


def test_maps_empty_optional_event_fields() -> None:
    model = _outbox_model(AuditEventDTO(action="health"))

    assert model.payload["node_id"] is None
    assert model.payload["details"] is None


async def test_lists_filtered_audit_logs() -> None:
    model = _log()
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows = MagicMock()
    rows.scalars.return_value = [model]
    session = AsyncMock()
    session.execute.side_effect = [count_result, rows]
    gateway = SqlAlchemyAuditLogGateway(as_typed(_Sessionmaker(session)))

    page = await gateway.list_logs(
        AuditLogQueryDTO(
            node_id=model.node_id,
            action="execute",
            offset=0,
            limit=20,
        )
    )

    assert page.total == 1
    assert page.items[0].id == model.id


async def test_lists_audit_logs_with_all_filters() -> None:
    model = _log()
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1
    rows = MagicMock()
    rows.scalars.return_value = [model]
    session = AsyncMock()
    session.execute.side_effect = [count_result, rows]
    gateway = SqlAlchemyAuditLogGateway(as_typed(_Sessionmaker(session)))

    page = await gateway.list_logs(
        AuditLogQueryDTO(
            node_id=model.node_id,
            action="execute",
            user="admin",
            date_from=datetime(2025, 1, 1, tzinfo=UTC),
            date_to=datetime(2025, 12, 31, tzinfo=UTC),
            offset=0,
            limit=20,
        )
    )

    assert page.total == 1
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    rows = MagicMock()
    rows.scalars.return_value = []
    session = AsyncMock()
    session.execute.side_effect = [count_result, rows]
    gateway = SqlAlchemyAuditLogGateway(as_typed(_Sessionmaker(session)))

    page = await gateway.list_logs(AuditLogQueryDTO(offset=5, limit=10))

    assert page.total == 0
    assert page.items == ()


async def test_delete_before_returns_rowcount_or_zero() -> None:
    cursor = MagicMock(spec=CursorResult)
    cursor.rowcount = 3
    session = AsyncMock()
    session.execute.side_effect = [cursor, MagicMock()]
    gateway = SqlAlchemyAuditLogGateway(as_typed(_Sessionmaker(session)))
    cutoff = datetime.now(UTC)

    assert await gateway.delete_before(cutoff) == 3
    assert await gateway.delete_before(cutoff) == 0


async def test_request_and_required_outboxes_flush_events() -> None:
    event = AuditEventDTO(action="execute", details={"result": "ok"})
    request_session = AsyncMock()
    request_session.add = MagicMock()
    required_session = AsyncMock()
    required_session.add = MagicMock()

    await RequestAuditOutbox(request_session).enqueue(event)
    await RequiredAuditOutbox(as_typed(_Sessionmaker(required_session))).enqueue(event)

    request_session.add.assert_called_once()
    request_session.flush.assert_awaited_once()
    required_session.add.assert_called_once()
    required_session.flush.assert_awaited_once()
