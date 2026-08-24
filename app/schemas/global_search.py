import uuid

from pydantic import BaseModel, ConfigDict


class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: str


class GlobalSearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    nodes: list[SearchResultItem]
    commands: list[SearchResultItem]
    scripts: list[SearchResultItem]
    tags: list[str]
