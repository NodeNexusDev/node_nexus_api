"""Global search API schemas."""

import uuid

from pydantic import BaseModel, ConfigDict


class SearchResultItem(BaseModel):
    """A single entity returned by global search."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: str


class GlobalSearchResponse(BaseModel):
    """Aggregated global search results across entities."""

    model_config = ConfigDict(from_attributes=True)

    nodes: list[SearchResultItem]
    commands: list[SearchResultItem]
    scripts: list[SearchResultItem]
    tags: list[str]
