"""Note API schemas."""

from datetime import datetime

from pydantic import BaseModel


class NoteCreate(BaseModel):
    """Request body for creating a note on any entity."""

    target_type: str
    target_id: str
    content: str


class NoteUpdate(BaseModel):
    """Request body for updating a note."""

    content: str


class NoteResponse(BaseModel):
    """Note response schema."""

    id: str
    target_type: str
    target_id: str
    content: str
    created_at: datetime
    updated_at: datetime
