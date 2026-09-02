"""Template registry persistence ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.dto.template_registry import (
    RegistryCreateDTO,
    RegistryPageDTO,
    RegistrySyncResultDTO,
    RegistryViewDTO,
)


class TemplateRegistryReader(Protocol):
    """Read registry views."""

    async def get_registry(self, registry_id: UUID) -> RegistryViewDTO | None:
        """Return one registry."""
        ...

    async def list_registries(self, offset: int, limit: int) -> RegistryPageDTO:
        """Return one page."""
        ...


class TemplateRegistryWriter(Protocol):
    """Persist registry mutations."""

    async def create_registry(self, data: RegistryCreateDTO) -> RegistryViewDTO:
        """Create a registry."""
        ...

    async def delete_registry(self, registry_id: UUID) -> bool:
        """Delete and report."""
        ...

    async def sync_registry(self, registry_id: UUID) -> RegistrySyncResultDTO:
        """Sync packs from GitHub."""
        ...
