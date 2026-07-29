"""Unit tests for persistent schedule orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import (
    NodeNotFoundError,
    ScheduleNotFoundError,
    SchedulePersistenceError,
    ScheduleValidationError,
    ScriptNotFoundError,
)
from app.schemas.scheduler import ScheduleRequest
from app.services.schedule_service import ScheduleService


def _service() -> tuple[ScheduleService, AsyncMock, AsyncMock, AsyncMock, MagicMock]:
    repository = AsyncMock()
    script_repository = AsyncMock()
    node_repository = AsyncMock()
    scheduler = MagicMock()
    return (
        ScheduleService(
            repository,
            script_repository,
            node_repository,
            scheduler,
        ),
        repository,
        script_repository,
        node_repository,
        scheduler,
    )


def _schedule(script_id, node_id):
    return SimpleNamespace(
        id=uuid4(),
        script_id=script_id,
        cron="0 9 * * *",
        timezone="UTC",
        node_ids=[str(node_id)],
        params={},
        enabled=True,
        misfire_grace_seconds=60,
        operational_state="registered",
        last_error_type=None,
        last_run_at=None,
        last_success_at=None,
        last_failure_at=None,
        next_run_at=None,
    )


async def test_create_persists_and_registers_runtime_job() -> None:
    service, repository, scripts, nodes, scheduler = _service()
    script_id, node_id = uuid4(), uuid4()
    scripts.get_by_id.return_value = object()
    nodes.get_by_id.return_value = object()
    repository.upsert.return_value = _schedule(script_id, node_id)

    result = await service.create_or_update(
        script_id,
        ScheduleRequest(cron="0 9 * * *", node_ids=[node_id]),
    )

    assert result.script_id == script_id
    repository.upsert.assert_awaited_once()
    scheduler.schedule_script.assert_called_once()


async def test_create_rejects_missing_script_before_side_effects() -> None:
    service, repository, scripts, _, scheduler = _service()
    scripts.get_by_id.return_value = None

    with pytest.raises(ScriptNotFoundError):
        await service.create_or_update(
            uuid4(), ScheduleRequest(cron="0 9 * * *", node_ids=[uuid4()])
        )

    repository.upsert.assert_not_called()
    scheduler.schedule_script.assert_not_called()


async def test_create_rejects_missing_node() -> None:
    service, repository, scripts, nodes, _ = _service()
    scripts.get_by_id.return_value = object()
    nodes.get_by_id.return_value = None

    with pytest.raises(NodeNotFoundError):
        await service.create_or_update(
            uuid4(), ScheduleRequest(cron="0 9 * * *", node_ids=[uuid4()])
        )

    repository.upsert.assert_not_called()


@pytest.mark.parametrize(
    ("cron", "timezone"),
    [("invalid", "UTC"), ("0 9 * * *", "Not/AZone")],
)
async def test_create_rejects_invalid_trigger(cron: str, timezone: str) -> None:
    service, repository, scripts, _, _ = _service()
    scripts.get_by_id.return_value = object()

    with pytest.raises(ScheduleValidationError):
        await service.create_or_update(
            uuid4(),
            ScheduleRequest(cron=cron, timezone=timezone, node_ids=[uuid4()]),
        )

    repository.upsert.assert_not_called()


async def test_restore_is_idempotent_via_replace_existing_registration() -> None:
    service, repository, _, _, scheduler = _service()
    script_id, node_id = uuid4(), uuid4()
    repository.list_enabled.return_value = [_schedule(script_id, node_id)]

    assert await service.restore() == (1, 0)
    assert await service.restore() == (1, 0)
    assert scheduler.schedule_script.call_count == 2


async def test_delete_missing_schedule() -> None:
    service, repository, _, _, scheduler = _service()
    repository.delete_by_script_id.return_value = False

    with pytest.raises(ScheduleNotFoundError):
        await service.delete(uuid4())

    scheduler.unschedule_script.assert_not_called()


async def test_runtime_registration_failure_is_persisted() -> None:
    service, repository, scripts, nodes, scheduler = _service()
    script_id, node_id = uuid4(), uuid4()
    scripts.get_by_id.return_value = object()
    nodes.get_by_id.return_value = object()
    schedule = _schedule(script_id, node_id)
    repository.upsert.return_value = schedule
    scheduler.schedule_script.side_effect = ValueError("invalid")

    with pytest.raises(SchedulePersistenceError):
        await service.create_or_update(
            script_id, ScheduleRequest(cron="0 9 * * *", node_ids=[node_id])
        )
    assert schedule.operational_state == "registration_failed"
    assert schedule.last_error_type == "ValueError"


async def test_get_and_delete_schedule() -> None:
    service, repository, _, _, scheduler = _service()
    script_id, node_id = uuid4(), uuid4()
    repository.get_by_script_id.return_value = _schedule(script_id, node_id)
    assert (await service.get(script_id)).script_id == script_id
    repository.delete_by_script_id.return_value = True
    await service.delete(script_id)
    scheduler.unschedule_script.assert_called_once_with(script_id)


async def test_get_missing_schedule() -> None:
    service, repository, _, _, _ = _service()
    repository.get_by_script_id.return_value = None
    with pytest.raises(ScheduleNotFoundError):
        await service.get(uuid4())


async def test_execution_metadata_transitions() -> None:
    service, repository, _, _, _ = _service()
    script_id, node_id = uuid4(), uuid4()
    schedule = _schedule(script_id, node_id)
    repository.get_by_script_id.return_value = schedule

    await service.mark_started(script_id)
    await service.mark_failed(script_id, "TimeoutError")
    assert schedule.last_run_at is not None
    assert schedule.last_failure_at is not None
    assert schedule.last_error_type == "TimeoutError"
    await service.mark_succeeded(script_id)
    assert schedule.last_success_at is not None
    assert schedule.last_error_type is None


async def test_metadata_missing_schedule_is_noop() -> None:
    service, repository, _, _, _ = _service()
    repository.get_by_script_id.return_value = None
    script_id = uuid4()
    await service.mark_started(script_id)
    await service.mark_succeeded(script_id)
    await service.mark_failed(script_id, "Error")
    repository.commit.assert_not_awaited()


async def test_restore_removes_orphan_and_records_failure() -> None:
    service, repository, _, _, scheduler = _service()
    script_id, node_id = uuid4(), uuid4()
    schedule = _schedule(script_id, node_id)
    repository.list_enabled.return_value = [schedule]
    scheduler.list_schedules.return_value = [{"job_id": str(uuid4())}]
    scheduler.schedule_script.side_effect = ValueError("invalid")

    assert await service.restore() == (0, 1)
    scheduler.unschedule_script.assert_called_once()
    assert schedule.operational_state == "registration_failed"
