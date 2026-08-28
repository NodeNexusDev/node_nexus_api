"""Tests for immutable script application contracts."""

import uuid
from datetime import UTC, datetime

import pytest

from app.application.dto.node_connection import NodeConnectionDTO
from app.application.dto.script_execution import (
    ResolvedScriptStepDTO,
    ScriptExecutionRequestDTO,
    ScriptExecutionTargetDTO,
)
from app.application.dto.script_management import (
    ScriptStepDTO,
    ScriptUpdateDTO,
    ScriptViewDTO,
)


def test_script_update_preserves_explicit_null() -> None:
    update = ScriptUpdateDTO(changes=(("description", None),))
    assert dict(update.changes) == {"description": None}


def test_script_view_is_immutable() -> None:
    now = datetime.now(UTC)
    view = ScriptViewDTO(
        id=uuid.uuid4(),
        name="deploy",
        description=None,
        steps=(ScriptStepDTO(label="check", type="inline", command="true"),),
        tags=("ops",),
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(AttributeError):
        setattr(view, "name", "changed")


def test_execution_target_contains_only_immutable_contracts() -> None:
    node = NodeConnectionDTO(
        id=uuid.uuid4(),
        name="node",
        host="127.0.0.1",
        port=22,
        connection_type="ssh",
        username="root",
    )
    request = ScriptExecutionRequestDTO(
        node_ids=(node.id,),
        params=(("environment", "prod"),),
    )
    target = ScriptExecutionTargetDTO(
        execution_id=uuid.uuid4(),
        script_id=uuid.uuid4(),
        node=node,
        steps=(
            ResolvedScriptStepDTO(
                label="deploy",
                command="true",
                on_failure="stop",
            ),
        ),
    )
    assert target.node.id == request.node_ids[0]
    assert target.steps[0].command == "true"
