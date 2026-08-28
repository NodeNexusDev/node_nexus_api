"""Unit tests for the short-scope schedule persistence adapter."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.adapters.persistence.schedule import SqlAlchemyScheduleGateway
from app.application.dto.schedule import ScheduleRequestDTO
from app.models.script_schedule import ScriptScheduleModel
from tests.typing import as_typed


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

    def __call__(self) -> _TransactionContext:
        return _TransactionContext(self._session)


def _result(*, scalar: object = None, scalars: list[object] | None = None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value = scalars or []
    return result


def _schedule(script_id: object | None = None) -> ScriptScheduleModel:
    return ScriptScheduleModel(
        id=uuid4(),
        script_id=script_id or uuid4(),
        cron="0 9 * * *",
        timezone="UTC",
        node_ids=[str(uuid4())],
        params={"environment": "prod"},
        enabled=True,
        misfire_grace_seconds=60,
        operational_state="registered",
    )


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
    gateway = SqlAlchemyScheduleGateway(as_typed(sessionmaker))
    script_id = uuid4()
    occurred_at = datetime.now(UTC)

    await gateway.mark_failed(script_id, occurred_at, "RuntimeError")

    session.execute.assert_awaited_once()


async def test_get_and_list_schedules_map_query_results() -> None:
    model = _schedule()
    session = AsyncMock()
    session.execute.side_effect = [
        _result(scalar=model),
        _result(scalars=[model]),
    ]
    gateway = SqlAlchemyScheduleGateway(as_typed(_Sessionmaker(session)))

    found = await gateway.get_schedule(model.script_id)
    enabled = await gateway.list_enabled_schedules()

    assert found is not None
    assert found.script_id == model.script_id
    assert [item.script_id for item in enabled] == [model.script_id]


async def test_get_schedule_returns_none() -> None:
    session = AsyncMock()
    session.execute.return_value = _result()
    gateway = SqlAlchemyScheduleGateway(as_typed(_Sessionmaker(session)))

    assert await gateway.get_schedule(uuid4()) is None


async def test_upsert_creates_and_updates_schedule() -> None:
    node_id = uuid4()
    data = ScheduleRequestDTO(
        cron="*/5 * * * *",
        timezone="Europe/Moscow",
        node_ids=(node_id,),
        params=(("mode", "safe"),),
        misfire_grace_seconds=90,
    )
    session = AsyncMock()
    session.add = MagicMock()
    session.execute.side_effect = [_result(), _result(scalar=_schedule())]
    gateway = SqlAlchemyScheduleGateway(as_typed(_Sessionmaker(session)))

    created = await gateway.upsert_schedule(uuid4(), data)
    updated = await gateway.upsert_schedule(uuid4(), data)

    session.add.assert_called_once()
    assert created.cron == "*/5 * * * *"
    assert updated.timezone == "Europe/Moscow"
    assert updated.operational_state == "pending_registration"
    assert updated.node_ids == (node_id,)


async def test_delete_schedule_handles_missing_and_existing() -> None:
    model = _schedule()
    session = AsyncMock()
    session.execute.side_effect = [_result(), _result(scalar=model)]
    gateway = SqlAlchemyScheduleGateway(as_typed(_Sessionmaker(session)))

    assert await gateway.delete_schedule(uuid4()) is False
    assert await gateway.delete_schedule(model.script_id) is True
    session.delete.assert_awaited_once_with(model)
    assert session.flush.await_count == 1


async def test_schedule_state_helpers_delegate_updates() -> None:
    session = AsyncMock()
    gateway = SqlAlchemyScheduleGateway(as_typed(_Sessionmaker(session)))
    script_id = uuid4()
    occurred_at = datetime.now(UTC)

    await gateway.mark_registration(
        script_id,
        state="registered",
        error_type=None,
        next_run_at=occurred_at,
    )
    await gateway.mark_started(script_id, occurred_at)
    await gateway.mark_succeeded(script_id, occurred_at)
    await gateway.mark_failed(script_id, occurred_at, "RuntimeError")

    assert session.execute.await_count == 4
