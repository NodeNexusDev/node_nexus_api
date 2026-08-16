from __future__ import annotations

from app.application.dto.global_search import (
    GlobalSearchQueryDTO,
    GlobalSearchResultDTO,
)
from app.application.ports.global_search import GlobalSearchReader


class GlobalSearchService:
    def __init__(self, reader: GlobalSearchReader) -> None:
        self._reader = reader

    async def search(
        self, q: str, limit: int = 20,
    ) -> GlobalSearchResultDTO:
        return await self._reader.search(
            GlobalSearchQueryDTO(q=q, limit=limit),
        )
