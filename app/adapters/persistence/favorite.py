"""Favorite persistence adapter."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.favorite import FavoriteCreateDTO, FavoriteDTO
from app.models.favorite import FavoriteModel


def _dto(m: FavoriteModel) -> FavoriteDTO:
    return FavoriteDTO(
        id=m.id,
        target_type=m.target_type,
        target_id=m.target_id,
        note=m.note,
        created_at=m.created_at,
    )


class SqlAlchemyFavoriteGateway:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_favorites(
        self,
        target_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FavoriteDTO], int]:
        q = select(FavoriteModel)
        if target_type:
            q = q.where(FavoriteModel.target_type == target_type)
        q = q.order_by(FavoriteModel.created_at.desc())

        total_q = select(func.count()).select_from(FavoriteModel)
        if target_type:
            total_q = total_q.where(FavoriteModel.target_type == target_type)

        total = (await self._session.execute(total_q)).scalar() or 0
        stmt = q.offset(offset).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_dto(r) for r in rows], total

    async def get_favorite(
        self, target_type: str, target_id: uuid.UUID,
    ) -> FavoriteDTO | None:
        q = select(FavoriteModel).where(
            FavoriteModel.target_type == target_type,
            FavoriteModel.target_id == target_id,
        )
        row = (await self._session.execute(q)).scalar_one_or_none()
        return _dto(row) if row else None

    async def add_favorite(self, data: FavoriteCreateDTO) -> FavoriteDTO:
        model = FavoriteModel(
            id=uuid.uuid4(),
            target_type=data.target_type,
            target_id=data.target_id,
            note=data.note,
        )
        self._session.add(model)
        await self._session.flush()
        return _dto(model)

    async def remove_favorite(
        self, target_type: str, target_id: uuid.UUID,
    ) -> bool:
        q = select(FavoriteModel).where(
            FavoriteModel.target_type == target_type,
            FavoriteModel.target_id == target_id,
        )
        row = (await self._session.execute(q)).scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        return True
