"""Note persistence adapter."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.note import NoteCreateDTO, NoteDTO, NoteUpdateDTO
from app.models.note import NoteModel


def _dto(m: NoteModel) -> NoteDTO:
    return NoteDTO(
        id=uuid.UUID(str(m.id)),
        target_type=m.target_type,
        target_id=uuid.UUID(str(m.target_id)),
        content=m.content,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyNoteGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_notes(
        self,
        target_type: str,
        target_id: uuid.UUID,
    ) -> list[NoteDTO]:
        q = (
            select(NoteModel)
            .where(
                NoteModel.target_type == target_type,
                NoteModel.target_id == target_id,
            )
            .order_by(NoteModel.created_at.desc())
        )
        rows = (await self._session.execute(q)).scalars().all()
        return [_dto(r) for r in rows]

    async def get_note(self, note_id: uuid.UUID) -> NoteDTO | None:
        q = select(NoteModel).where(NoteModel.id == note_id)
        row = (await self._session.execute(q)).scalar_one_or_none()
        return _dto(row) if row else None

    async def create_note(self, data: NoteCreateDTO) -> NoteDTO:
        model = NoteModel(
            id=uuid.uuid4(),
            target_type=data.target_type,
            target_id=data.target_id,
            content=data.content,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return _dto(model)

    async def update_note(
        self,
        note_id: uuid.UUID,
        data: NoteUpdateDTO,
    ) -> NoteDTO | None:
        q = select(NoteModel).where(NoteModel.id == note_id)
        row = (await self._session.execute(q)).scalar_one_or_none()
        if row is None:
            return None
        row.content = data.content
        await self._session.flush()
        await self._session.refresh(row)
        return _dto(row)

    async def delete_note(self, note_id: uuid.UUID) -> bool:
        q = select(NoteModel).where(NoteModel.id == note_id)
        row = (await self._session.execute(q)).scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
