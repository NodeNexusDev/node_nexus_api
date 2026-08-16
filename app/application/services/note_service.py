"""Note application service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.application.dto.note import NoteCreateDTO, NoteDTO, NoteUpdateDTO
from app.core.exceptions import NoteNotFoundError

if TYPE_CHECKING:
    from app.application.ports.note import NoteReader, NoteWriter


class NoteService:
    def __init__(
        self,
        reader: NoteReader,
        writer: NoteWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def list_notes(
        self, target_type: str, target_id: str,
    ) -> list[NoteDTO]:
        return await self._reader.list_notes(target_type, UUID(target_id))

    async def get_note(self, note_id: str) -> NoteDTO:
        note = await self._reader.get_note(UUID(note_id))
        if note is None:
            raise NoteNotFoundError(f"Note {note_id} not found")
        return note

    async def create_note(self, data: NoteCreateDTO) -> NoteDTO:
        return await self._writer.create_note(data)

    async def update_note(
        self, note_id: str, data: NoteUpdateDTO,
    ) -> NoteDTO:
        note = await self._writer.update_note(UUID(note_id), data)
        if note is None:
            raise NoteNotFoundError(f"Note {note_id} not found")
        return note

    async def delete_note(self, note_id: str) -> bool:
        deleted = await self._writer.delete_note(UUID(note_id))
        if not deleted:
            raise NoteNotFoundError(f"Note {note_id} not found")
        return True
