"""Favorite persistence port."""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from app.application.dto.favorite import FavoriteCreateDTO, FavoriteDTO


@runtime_checkable
class FavoriteReader(Protocol):
    async def list_favorites(
        self,
        target_type: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[FavoriteDTO], int]: ...

    async def get_favorite(
        self,
        target_type: str,
        target_id: uuid.UUID,
    ) -> FavoriteDTO | None: ...


@runtime_checkable
class FavoriteWriter(Protocol):
    async def add_favorite(self, data: FavoriteCreateDTO) -> FavoriteDTO: ...
    async def remove_favorite(
        self,
        target_type: str,
        target_id: uuid.UUID,
    ) -> bool: ...
