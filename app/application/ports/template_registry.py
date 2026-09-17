"""Template registry persistence ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.dto.template_registry import (
    RegistryCreateDTO,
    RegistryPageDTO,
    RegistryUpdateDTO,
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

    async def delete_registry(self, registry_id: UUID) -> None:
        """Delete or raise when missing."""
        ...

    async def patch_registry(
        self, registry_id: UUID, data: RegistryUpdateDTO
    ) -> RegistryViewDTO:
        """Partial update (owner/name/branch/token)."""
        ...

    async def get_registry_token(self, registry_id: UUID) -> str | None:
        """Return the decrypted GitHub token for sync (internal use)."""
        ...

    async def touch_synced(self, registry_id: UUID) -> RegistryViewDTO:
        """Mark registry synced now."""
        ...


class TemplateRegistryGateway(TemplateRegistryReader, TemplateRegistryWriter, Protocol):
    """Full registry persistence port."""
