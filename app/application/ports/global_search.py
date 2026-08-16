from __future__ import annotations

from typing import Protocol

from app.application.dto.global_search import (
    GlobalSearchQueryDTO,
    GlobalSearchResultDTO,
)


class GlobalSearchReader(Protocol):
    async def search(
        self,
        query: GlobalSearchQueryDTO,
    ) -> GlobalSearchResultDTO: ...
