"""Note persistence port."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from app.application.dto.note import NoteCreateDTO, NoteDTO, NoteUpdateDTO


@runtime_checkable
class NoteReader(Protocol):
    async def list_notes(
        self,
        target_type: str,
        target_id: uuid.UUID,
    ) -> list[NoteDTO]: ...

    async def get_note(self, note_id: uuid.UUID) -> NoteDTO | None: ...


@runtime_checkable
class NoteWriter(Protocol):
    async def create_note(self, data: NoteCreateDTO) -> NoteDTO: ...
    async def update_note(
        self, note_id: uuid.UUID, data: NoteUpdateDTO,
    ) -> NoteDTO | None: ...
    async def delete_note(self, note_id: uuid.UUID) -> bool: ...
