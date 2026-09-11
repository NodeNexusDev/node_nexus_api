"""Shared helpers for API v2 handlers — DRY command/pack pagination."""  # noqa: E501

from __future__ import annotations

from fastapi import HTTPException

from app.api.pagination import decode_offset, encode_offset
from app.application.dto.command_management import CommandViewDTO
from app.application.dto.script_management import ScriptViewDTO
from app.application.dto.template_pack import PackDetailDTO, PackViewDTO
from app.application.dto.template_registry import RegistryViewDTO
from app.schemas.command import CommandParameter, CommandResponse
from app.schemas.script import ScriptResponse, ScriptStep
from app.schemas.template_pack import (
    PackAssetResponse,
    PackDetailWithAssetsResponse,
    PackResponse,
)
from app.schemas.template_registry import RegistryResponse

# Re-export pagination helpers to avoid per-file alias
__all__ = [
    "decode_offset",
    "encode_offset",
    "command_response",
    "script_response",
    "pack_response",
    "registry_response",
    "pack_detail_response",
    "parse_cursor_offset",
    "pagination_params",
    "cursor_next",
    "_command_response",
    "_pack_response",
    "_registry_response",
    "_encode_offset",
    "_decode_offset",
]

# Compatibility aliases for N816 usage
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816


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


# Backwards-compat alias for tests importing private name
_command_response = command_response  # noqa: N816


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


_script_response = script_response  # noqa: N816


def pack_response(view: PackViewDTO) -> PackResponse:
    """Map PackViewDTO to PackResponse."""
    return PackResponse(
        id=view.id,
        registry_id=view.registry_id,
        pack_id=view.pack_id,
        name=view.name,
        description=view.description,
        version=view.version,
        author=view.author,
        tags=list(view.tags) if view.tags else [],
        manifest_sha=view.manifest_sha,
        readme=view.readme,
        installed_version=view.installed_version,
        installed_at=view.installed_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


_pack_response = pack_response  # noqa: N816


def registry_response(view: RegistryViewDTO) -> RegistryResponse:
    """Map RegistryViewDTO to RegistryResponse."""
    return RegistryResponse(
        id=view.id,
        owner=view.owner,
        name=view.name,
        default_branch=view.default_branch,
        last_synced_at=view.last_synced_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


_registry_response = registry_response  # noqa: N816


def pack_detail_response(detail: PackDetailDTO) -> PackDetailWithAssetsResponse:
    """Map PackDetailDTO to PackDetailWithAssetsResponse."""
    view = detail.pack
    assets = [
        PackAssetResponse(
            id=a.id,
            pack_id=a.pack_id,
            path=a.path,
            size=a.size,
            sha=a.sha,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in detail.assets
    ]
    return PackDetailWithAssetsResponse(
        id=view.id,
        registry_id=view.registry_id,
        pack_id=view.pack_id,
        name=view.name,
        description=view.description,
        version=view.version,
        author=view.author,
        tags=list(view.tags) if view.tags else [],
        manifest_sha=view.manifest_sha,
        readme=view.readme,
        installed_version=view.installed_version,
        installed_at=view.installed_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
        assets=assets,
    )


_pack_detail_response = pack_detail_response  # noqa: N816


# ---------------------------------------------------------------------------
# Pagination offset helpers (cursor = base64 offset)
# ---------------------------------------------------------------------------


def parse_cursor_offset(cursor: str | None) -> int:
    """Parse cursor to offset, raising 422 on invalid."""
    if cursor is None or cursor == "":
        return 0
    try:
        return decode_offset(cursor)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid cursor") from None


def pagination_params(offset: int, limit: int) -> tuple[int, int, int]:
    """Translate offset/limit to page/fetch_size/remainder for offset-based services.

    Returns (page, fetch_size, remainder) where page is 1-based.
    """
    remainder = offset % limit if limit else 0
    page = offset // limit + 1 if limit else 1
    fetch_size = limit + remainder if remainder else limit
    return page, fetch_size, remainder


def cursor_next(  # noqa: E501
    offset: int, limit: int, total: int, returned: int
) -> tuple[str | None, bool]:
    """Build next_cursor and has_more from offset/limit/total."""
    has_more = (offset + returned) < total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return next_cursor, has_more
