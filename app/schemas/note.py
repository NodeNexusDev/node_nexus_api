"""Note API schemas."""

from datetime import datetime

from pydantic import BaseModel


class NoteCreate(BaseModel):
    target_type: str
    target_id: str
    content: str


class NoteUpdate(BaseModel):
    content: str


class NoteResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    content: str
    created_at: datetime
    updated_at: datetime
