"""Tests for strict-typing validation branches added in 1.4.0."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.adapters.persistence.dao.execution_stats import ExecutionStatsRepository
from app.adapters.persistence.script_gateway import SqlAlchemyScriptGateway
from app.application.dto.script_management import ScriptUpdateDTO
from app.models.script_execution import ScriptExecutionModel
from tests.typing import as_unvalidated

# ─── script_gateway helpers ──────────────────────────────────────────────────


def test_step_from_dict_rejects_invalid_type() -> None:
    with pytest.raises(ValueError, match="Stored script step type is invalid"):
        SqlAlchemyScriptGateway._step_from_dict(
            {
                "label": "check",
                "type": "bad",
                "on_failure": "stop",
            }
        )


def test_step_from_dict_rejects_invalid_failure_policy() -> None:
    with pytest.raises(ValueError, match="Stored script failure policy is invalid"):
        SqlAlchemyScriptGateway._step_from_dict(
            {
                "label": "check",
                "type": "inline",
                "on_failure": "bad",
            }
        )


def test_step_from_dict_rejects_non_object_params() -> None:
    with pytest.raises(ValueError, match="Stored script step params must be an object"):
        SqlAlchemyScriptGateway._step_from_dict(
            {
                "label": "check",
                "type": "inline",
                "params": "not-a-dict",
                "on_failure": "stop",
            }
        )


def test_step_from_dict_rejects_missing_label() -> None:
    with pytest.raises(ValueError, match="Stored field 'label' must be a string"):
        SqlAlchemyScriptGateway._step_from_dict(
            {
                "type": "inline",
                "on_failure": "stop",
            }
        )


def test_step_from_dict_rejects_non_string_command() -> None:
    with pytest.raises(
        ValueError, match="Stored field 'command' must be a string or null"
    ):
        SqlAlchemyScriptGateway._step_from_dict(
            {
                "label": "check",
                "type": "inline",
                "command": 123,
                "on_failure": "stop",
            }
        )


def test_step_result_rejects_bool_as_int() -> None:
    now = datetime.now(UTC)
    execution = ScriptExecutionModel(
        id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        params={},
        status="success",
        steps=[
            {
                "step_index": True,  # bool must be rejected
                "label": "run",
                "command_fingerprint": "abc",
                "stdout": "ok",
                "stderr": "",
                "stdout_bytes": 2,
                "stderr_bytes": 0,
                "truncated": False,
                "exit_code": 0,
            }
        ],
        started_at=now,
        finished_at=now,
    )
    with pytest.raises(
        ValueError, match="Stored field 'step_index' must be an integer"
    ):
        SqlAlchemyScriptGateway._to_execution(execution)


def test_step_result_rejects_non_bool_truncated() -> None:
    now = datetime.now(UTC)
    execution = ScriptExecutionModel(
        id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        status="success",
        steps=[
            {
                "step_index": 0,
                "label": "run",
                "command_fingerprint": "abc",
                "stdout": "ok",
                "stderr": "",
                "stdout_bytes": 2,
                "stderr_bytes": 0,
                "truncated": "yes",  # invalid
                "exit_code": 0,
            }
        ],
        started_at=now,
    )
    with pytest.raises(ValueError, match="Stored field 'truncated' must be a boolean"):
        SqlAlchemyScriptGateway._to_execution(execution)


def test_to_execution_rejects_invalid_status() -> None:
    now = datetime.now(UTC)
    execution = ScriptExecutionModel(
        id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        status="unknown_status",
        started_at=now,
    )
    with pytest.raises(ValueError, match="Stored script execution status is invalid"):
        SqlAlchemyScriptGateway._to_execution(execution)


@pytest.mark.asyncio
async def test_update_script_rejects_invalid_step_tuple() -> None:
    from unittest.mock import MagicMock

    factory = MagicMock()
    # pass an object that is not ScriptStepDTO inside tuple
    raw_changes: object = (("steps", ({"label": "bad"},)),)
    invalid_changes = as_unvalidated(ScriptUpdateDTO, raw_changes)

    with pytest.raises(TypeError, match="Script update contains an invalid step"):
        await SqlAlchemyScriptGateway(factory).update_script(
            uuid.uuid4(),
            ScriptUpdateDTO(changes=invalid_changes),
        )


# ─── execution_stats _validated_row ───────────────────────────────────────────


def test_validated_row_rejects_non_int_total() -> None:
    row: object = {
        "total": "5",
        "successful": 4,
        "failed": 1,
        "avg_duration_ms": 100.0,
        "min_duration_ms": 50.0,
        "max_duration_ms": 200.0,
        "last_executed_at": None,
    }
    with pytest.raises(TypeError, match="Statistics field 'total' must be an integer"):
        ExecutionStatsRepository._validated_row(
            as_unvalidated(Mapping[object, object], row),
        )


def test_validated_row_rejects_bool_total() -> None:
    row: object = {
        "total": True,
        "successful": 0,
        "failed": 0,
        "avg_duration_ms": None,
        "min_duration_ms": None,
        "max_duration_ms": None,
        "last_executed_at": None,
    }
    with pytest.raises(TypeError, match="Statistics field 'total' must be an integer"):
        ExecutionStatsRepository._validated_row(
            as_unvalidated(Mapping[object, object], row),
        )


def test_validated_row_rejects_non_numeric_avg() -> None:
    row: object = {
        "total": 1,
        "successful": 1,
        "failed": 0,
        "avg_duration_ms": "fast",
        "min_duration_ms": None,
        "max_duration_ms": None,
        "last_executed_at": None,
    }
    with pytest.raises(
        TypeError, match="Statistics field 'avg_duration_ms' must be numeric"
    ):
        ExecutionStatsRepository._validated_row(
            as_unvalidated(Mapping[object, object], row),
        )


def test_validated_row_rejects_wrong_last_executed_at_type() -> None:
    row: object = {
        "total": 1,
        "successful": 1,
        "failed": 0,
        "avg_duration_ms": None,
        "min_duration_ms": None,
        "max_duration_ms": None,
        "last_executed_at": "2026-01-01",
    }
    with pytest.raises(
        TypeError, match="Statistics last_executed_at must be a datetime"
    ):
        ExecutionStatsRepository._validated_row(
            as_unvalidated(Mapping[object, object], row),
        )


def test_validated_row_accepts_decimal_and_int() -> None:
    now = datetime.now(UTC)
    row: object = {
        "total": 2,
        "successful": 1,
        "failed": 1,
        "avg_duration_ms": Decimal("123.45"),
        "min_duration_ms": 10,  # int should be coerced to float
        "max_duration_ms": 200.0,
        "last_executed_at": now,
    }
    result = ExecutionStatsRepository._validated_row(
        as_unvalidated(Mapping[object, object], row),
    )

    assert result["total"] == 2
    assert result["avg_duration_ms"] == pytest.approx(123.45)
    assert result["min_duration_ms"] == pytest.approx(10.0)
    assert result["last_executed_at"] == now


@pytest.mark.asyncio
async def test_execution_stats_repository_returns_empty_on_no_row() -> None:
    from unittest.mock import MagicMock

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    session.execute.return_value = mock_result

    repo = ExecutionStatsRepository(session)
    result = await repo.command_stats(command_id=uuid.uuid4())

    assert result["total"] == 0
    assert result["last_executed_at"] is None
