"""Unit tests for the short-scope schedule persistence adapter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from app.adapters.persistence.schedule import SqlAlchemyScheduleGateway
from app.models.script_schedule import ScriptScheduleModel


class _TransactionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


class _Sessionmaker:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    def begin(self) -> _TransactionContext:
        return _TransactionContext(self._session)


def test_maps_orm_model_to_immutable_application_view() -> None:
    schedule_id = uuid4()
    script_id = uuid4()
    node_id = uuid4()
    occurred_at = datetime.now(UTC)
    model = ScriptScheduleModel(
        id=schedule_id,
        script_id=script_id,
        cron="0 9 * * *",
        timezone="UTC",
        node_ids=[str(node_id)],
        params={"environment": "prod"},
        enabled=True,
        misfire_grace_seconds=60,
        operational_state="registered",
        last_run_at=occurred_at,
    )

    view = SqlAlchemyScheduleGateway._to_view(model)

    assert view.id == schedule_id
    assert view.script_id == script_id
    assert view.node_ids == (node_id,)
    assert dict(view.params) == {"environment": "prod"}
    assert view.last_run_at == occurred_at


async def test_operational_update_owns_a_short_transaction() -> None:
    session = AsyncMock()
    sessionmaker = _Sessionmaker(session)
    gateway = SqlAlchemyScheduleGateway(sessionmaker)  # type: ignore[arg-type]
    script_id = uuid4()
    occurred_at = datetime.now(UTC)

    await gateway.mark_failed(script_id, occurred_at, "RuntimeError")

    session.execute.assert_awaited_once()
