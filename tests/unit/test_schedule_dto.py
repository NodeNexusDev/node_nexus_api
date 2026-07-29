"""Tests for immutable scheduler application contracts."""

import uuid

import pytest

from app.application.dto.schedule import (
    RuntimeScheduleDTO,
    ScheduleRequestDTO,
)


def test_schedule_request_uses_immutable_collections() -> None:
    node_id = uuid.uuid4()
    request = ScheduleRequestDTO(
        cron="0 9 * * *",
        node_ids=(node_id,),
        params=(("environment", "prod"),),
    )
    assert request.node_ids == (node_id,)
    assert dict(request.params) == {"environment": "prod"}


def test_runtime_schedule_is_immutable() -> None:
    runtime = RuntimeScheduleDTO(
        schedule_id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        cron="0 9 * * *",
        timezone="UTC",
        node_ids=(uuid.uuid4(),),
        params=(),
        misfire_grace_seconds=60,
    )
    with pytest.raises(AttributeError):
        runtime.cron = "* * * * *"  # type: ignore[misc]
