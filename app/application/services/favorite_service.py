"""Favorite application service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.dto.favorite import (
    FavoriteCreateDTO,
    FavoriteDTO,
    FavoriteUpdateDTO,
)
from app.core.exceptions import FavoriteNotFoundError

if TYPE_CHECKING:
    from app.application.ports.favorite import FavoriteReader, FavoriteWriter


class FavoriteService:
    def __init__(
        self,
        reader: FavoriteReader,
        writer: FavoriteWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def list_favorites(
        self,
        target_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[FavoriteDTO], int]:
        return await self._reader.list_favorites(
            target_type=target_type,
            offset=(page - 1) * size,
            limit=size,
        )

    async def add_favorite(self, data: FavoriteCreateDTO) -> FavoriteDTO:
        return await self._writer.add_favorite(data)

    async def get_favorite(self, target_type: str, target_id: str) -> FavoriteDTO:
        import uuid

        dto = await self._reader.get_favorite(target_type, uuid.UUID(target_id))
        if dto is None:
            raise FavoriteNotFoundError(f"Favorite {target_type}:{target_id} not found")
        return dto

    async def update_favorite(
        self, target_type: str, target_id: str, data: FavoriteUpdateDTO
    ) -> FavoriteDTO:
        import uuid

        updated = await self._writer.update_favorite(
            target_type, uuid.UUID(target_id), data
        )
        if updated is None:
            raise FavoriteNotFoundError(f"Favorite {target_type}:{target_id} not found")
        return updated

    async def remove_favorite(
        self,
        target_type: str,
        target_id: str,
    ) -> bool:
        import uuid

        removed = await self._writer.remove_favorite(
            target_type,
            uuid.UUID(target_id),
        )
        if not removed:
            raise FavoriteNotFoundError(f"Favorite {target_type}:{target_id} not found")
        return True
