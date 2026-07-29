"""Tests for the APScheduler runtime port adapter."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from app.adapters.runtime.scheduler import ApschedulerJobScheduler
from app.application.dto.schedule import RuntimeScheduleDTO


def test_add_or_replace_maps_runtime_schedule() -> None:
    scheduler = MagicMock()
    next_run = datetime.now(UTC)
    scheduler.get_next_run_time.return_value = next_run
    adapter = ApschedulerJobScheduler(scheduler)
    script_id = uuid4()
    schedule_id = uuid4()
    node_id = uuid4()

    result = adapter.add_or_replace(
        RuntimeScheduleDTO(
            schedule_id=schedule_id,
            script_id=script_id,
            cron="0 9 * * *",
            timezone="UTC",
            node_ids=(node_id,),
            params=(("environment", "prod"),),
            misfire_grace_seconds=60,
        )
    )

    scheduler.schedule_script.assert_called_once_with(
        script_id,
        "0 9 * * *",
        [node_id],
        params={"environment": "prod"},
        timezone="UTC",
        misfire_grace_seconds=60,
        schedule_id=schedule_id,
    )
    assert result.script_id == script_id
    assert result.next_run_at == next_run


def test_remove_and_inspect_map_runtime_state() -> None:
    script_id = uuid4()
    next_run = datetime.now(UTC)
    scheduler = MagicMock()
    scheduler.unschedule_script.return_value = True
    scheduler.list_schedules.return_value = [
        {
            "job_id": str(script_id),
            "next_run_time": next_run.isoformat(),
        }
    ]
    adapter = ApschedulerJobScheduler(scheduler)

    assert adapter.remove(script_id) is True
    assert adapter.inspect()[0].next_run_at == next_run


def test_exposes_readiness_and_ownership_without_concrete_type() -> None:
    scheduler = MagicMock(ready=True, owns_execution=False)
    adapter = ApschedulerJobScheduler(scheduler)

    assert adapter.is_ready() is True
    assert adapter.owns_execution() is False
