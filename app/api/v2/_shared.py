"""Shared helpers for API v2 handlers — DRY for _command_response etc."""

from __future__ import annotations

from app.api.pagination import decode_offset, encode_offset
from app.application.dto.command_management import CommandViewDTO
from app.application.dto.script_management import ScriptViewDTO
from app.schemas.command import CommandParameter, CommandResponse
from app.schemas.script import ScriptResponse, ScriptStep

# Re-export pagination helpers to avoid per-file alias
__all__ = [
    "decode_offset",
    "encode_offset",
    "command_response",
    "script_response",
]


def command_response(command: CommandViewDTO) -> CommandResponse:
    """Map CommandViewDTO to CommandResponse."""
    return CommandResponse(
        id=command.id,
        name=command.name,
        description=command.description,
        command=command.command,
        parameters=[
            CommandParameter(
                name=p.name,
                type=p.type,
                required=p.required,
                default=p.default,
                description=p.description,
            )
            for p in command.parameters
        ],
        tags=list(command.tags),
        timeout=command.timeout,
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


def script_response(script: ScriptViewDTO) -> ScriptResponse:
    """Map ScriptViewDTO to ScriptResponse."""
    return ScriptResponse(
        id=script.id,
        name=script.name,
        description=script.description,
        steps=[
            ScriptStep(
                label=s.label,
                type=s.type,
                command=s.command,
                command_id=s.command_id,
                params=dict(s.params),
                on_failure=s.on_failure,
            )
            for s in script.steps
        ],
        tags=list(script.tags),
        timeout=script.timeout,
        created_at=script.created_at,
        updated_at=script.updated_at,
    )
