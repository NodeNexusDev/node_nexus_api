"""Unit tests for scheduler application use cases."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.application.dto.schedule import (
    RuntimeJobViewDTO,
    ScheduleRequestDTO,
    ScheduleViewDTO,
)
from app.application.services.schedule_management import (
    ScheduleManagementService,
)
from app.application.services.schedule_reconciliation import (
    ScheduleReconciliationService,
)
from app.core.exceptions import (
    NodeNotFoundError,
    ScheduleNotFoundError,
    SchedulePersistenceError,
    ScheduleValidationError,
    ScriptNotFoundError,
)


def _view(script_id: UUID, node_id: UUID | None = None) -> ScheduleViewDTO:
    return ScheduleViewDTO(
        id=uuid4(),
        script_id=script_id,
        cron="0 9 * * *",
        timezone="UTC",
        node_ids=(node_id,) if node_id else (),
        params=(),
        enabled=True,
        misfire_grace_seconds=60,
        operational_state="pending_registration",
    )


def _management() -> tuple[
    ScheduleManagementService,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    AsyncMock,
    MagicMock,
]:
    reader = AsyncMock()
    writer = AsyncMock()
    scripts = AsyncMock()
    nodes = AsyncMock()
    scheduler = MagicMock()
    return (
        ScheduleManagementService(reader, writer, scripts, nodes, scheduler),
        reader,
        writer,
        scripts,
        nodes,
        scheduler,
    )


async def test_management_persists_then_applies_and_records_runtime() -> None:
    service, reader, writer, scripts, nodes, scheduler = _management()
    script_id, node_id = uuid4(), uuid4()
    desired = _view(script_id, node_id)
    registered = replace(
        desired,
        operational_state="registered",
        next_run_at=datetime.now(UTC),
    )
    scripts.get_script.return_value = object()
    nodes.get_node.return_value = object()
    writer.upsert_schedule.return_value = desired
    scheduler.add_or_replace.return_value = RuntimeJobViewDTO(
        script_id=script_id,
        next_run_at=registered.next_run_at,
    )
    reader.get_schedule.return_value = registered

    result = await service.create_or_update(
        script_id,
        ScheduleRequestDTO(cron="0 9 * * *", node_ids=(node_id,)),
    )

    assert result == registered
    writer.upsert_schedule.assert_awaited_once()
    scheduler.add_or_replace.assert_called_once()
    writer.mark_registration.assert_awaited_once_with(
        script_id,
        state="registered",
        error_type=None,
        next_run_at=registered.next_run_at,
    )


@pytest.mark.parametrize(
    ("missing", "error"),
    [("script", ScriptNotFoundError), ("node", NodeNotFoundError)],
)
async def test_management_validates_references_before_persisting(
    missing: str, error: type[Exception]
) -> None:
    service, _, writer, scripts, nodes, _ = _management()
    scripts.get_script.return_value = None if missing == "script" else object()
    nodes.get_node.return_value = None

    with pytest.raises(error):
        await service.create_or_update(
            uuid4(),
            ScheduleRequestDTO(cron="0 9 * * *", node_ids=(uuid4(),)),
        )
    writer.upsert_schedule.assert_not_awaited()


async def test_management_translates_trigger_validation_error() -> None:
    service, _, writer, scripts, _, scheduler = _management()
    scripts.get_script.return_value = object()
    scheduler.validate.side_effect = ValueError("bad cron")

    with pytest.raises(ScheduleValidationError):
        await service.create_or_update(
            uuid4(), ScheduleRequestDTO(cron="bad", node_ids=())
        )
    writer.upsert_schedule.assert_not_awaited()


async def test_management_records_runtime_registration_failure() -> None:
    service, _, writer, scripts, _, scheduler = _management()
    script_id = uuid4()
    scripts.get_script.return_value = object()
    writer.upsert_schedule.return_value = _view(script_id)
    scheduler.add_or_replace.side_effect = RuntimeError("scheduler unavailable")

    with pytest.raises(SchedulePersistenceError):
        await service.create_or_update(
            script_id, ScheduleRequestDTO(cron="0 9 * * *", node_ids=())
        )
    writer.mark_registration.assert_awaited_once_with(
        script_id,
        state="registration_failed",
        error_type="RuntimeError",
    )


async def test_management_get_and_delete_missing_schedule() -> None:
    service, reader, writer, _, _, scheduler = _management()
    reader.get_schedule.return_value = None
    writer.delete_schedule.return_value = False

    with pytest.raises(ScheduleNotFoundError):
        await service.get(uuid4())
    with pytest.raises(ScheduleNotFoundError):
        await service.delete(uuid4())
    scheduler.remove.assert_not_called()


async def test_reconciliation_removes_orphans_and_records_each_outcome() -> None:
    reader = AsyncMock()
    writer = AsyncMock()
    scheduler = MagicMock()
    first, second, orphan = uuid4(), uuid4(), uuid4()
    reader.list_enabled_schedules.return_value = [_view(first), _view(second)]
    scheduler.inspect.return_value = [
        RuntimeJobViewDTO(script_id=orphan, next_run_at=None)
    ]
    scheduler.add_or_replace.side_effect = [
        RuntimeJobViewDTO(script_id=first, next_run_at=None),
        ValueError("bad trigger"),
    ]
    service = ScheduleReconciliationService(reader, writer, scheduler)

    result = await service.reconcile()

    assert (result.restored, result.failed) == (1, 1)
    scheduler.remove.assert_called_once_with(orphan)
    assert writer.mark_registration.await_count == 2
