from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GlobalSearchQueryDTO:
    q: str
    limit: int = 20


@dataclass(frozen=True, slots=True)
class SearchResultItemDTO:
    id: uuid.UUID
    name: str
    entity_type: str


@dataclass(frozen=True, slots=True)
class GlobalSearchResultDTO:
    nodes: tuple[SearchResultItemDTO, ...]
    commands: tuple[SearchResultItemDTO, ...]
    scripts: tuple[SearchResultItemDTO, ...]
    tags: tuple[str, ...]
