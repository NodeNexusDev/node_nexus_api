"""Compose persistence ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.dto.compose import (
    ComposeCreateDTO,
    ComposeUpdateDTO,
    ComposeViewDTO,
)


class ComposeReader(Protocol):
    """Read compose projects."""

    async def get_project(
        self, node_id: UUID, project_name: str
    ) -> ComposeViewDTO | None:
        """Return one compose project or None."""
        ...

    async def list_projects(
        self, node_id: UUID, offset: int, limit: int
    ) -> list[ComposeViewDTO]:
        """Return a page of compose projects ordered by created_at desc."""
        ...

    async def count_projects(self, node_id: UUID) -> int:
        """Return total count for stats."""
        ...

    async def stats(self, node_id: UUID) -> int:
        """Alias for count_projects (stats)."""
        ...


class ComposeWriter(Protocol):
    """Write compose projects."""

    async def create_project(self, data: ComposeCreateDTO) -> ComposeViewDTO:
        """Create a compose project."""
        ...

    async def update_project(
        self, node_id: UUID, project_name: str, data: ComposeUpdateDTO
    ) -> ComposeViewDTO | None:
        """Update a compose project, return None if missing."""
        ...

    async def delete_project(self, node_id: UUID, project_name: str) -> bool:
        """Delete a compose project, return True if deleted."""
        ...

    async def upsert_project(self, data: ComposeCreateDTO) -> ComposeViewDTO:
        """Create or update a compose project."""
        ...
