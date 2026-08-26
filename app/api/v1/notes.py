"""Notes API endpoints."""

import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import (
    Principal,
    get_current_principal,
    require_write_or_jwt_scope,
)
from app.application.dto.note import NoteCreateDTO, NoteUpdateDTO
from app.application.services.note_service import NoteService
from app.schemas.note import NoteCreate, NoteResponse, NoteUpdate

audit = structlog.get_logger("audit")

router = APIRouter(tags=["notes"], route_class=DishkaRoute)


@router.get("/notes/{target_type}/{target_id}", response_model=list[NoteResponse])
@inject
async def list_notes(
    target_type: str,
    target_id: str,
    service: FromDishka[NoteService],
    _key: Principal = Security(get_current_principal),
) -> list[NoteResponse]:
    audit.info("api.notes.list", target=target_type + ":" + target_id)
    items = await service.list_notes(target_type, target_id)
    return [
        NoteResponse(
            id=str(n.id),
            target_type=n.target_type,
            target_id=str(n.target_id),
            content=n.content,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )
        for n in items
    ]


@router.post(
    "/notes/{target_type}/{target_id}",
    response_model=NoteResponse,
    status_code=201,
)
@inject
async def create_note(
    target_type: str,
    target_id: str,
    data: NoteCreate,
    service: FromDishka[NoteService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> NoteResponse:
    audit.info("api.notes.create", target=target_type + ":" + target_id)
    result = await service.create_note(
        NoteCreateDTO(
            target_type=target_type,
            target_id=uuid.UUID(target_id),
            content=data.content,
        )
    )
    return NoteResponse(
        id=str(result.id),
        target_type=result.target_type,
        target_id=str(result.target_id),
        content=result.content,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.put("/notes/{note_id}", response_model=NoteResponse)
@inject
async def update_note(
    note_id: str,
    data: NoteUpdate,
    service: FromDishka[NoteService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> NoteResponse:
    audit.info("api.notes.update", note_id=note_id)
    result = await service.update_note(note_id, NoteUpdateDTO(content=data.content))
    return NoteResponse(
        id=str(result.id),
        target_type=result.target_type,
        target_id=str(result.target_id),
        content=result.content,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


@router.delete("/notes/{note_id}", status_code=204)
@inject
async def delete_note(
    note_id: str,
    service: FromDishka[NoteService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> None:
    audit.info("api.notes.delete", note_id=note_id)
    await service.delete_note(note_id)
