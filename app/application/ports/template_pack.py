"""Template pack persistence ports."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.dto.template_pack import (
    PackCreateDTO,
    PackDetailDTO,
    PackInstallationPageDTO,
    PackInstallResultDTO,
    PackListQueryDTO,
    PackPageDTO,
    PackStatsDTO,
    PackViewDTO,
)


class TemplatePackReader(Protocol):
    """Read pack views."""

    async def get_pack(self, pack_id: UUID) -> PackDetailDTO | None:
        """Return one pack with assets."""
        ...

    async def list_packs(self, query: PackListQueryDTO) -> PackPageDTO:
        """Return one page."""
        ...

    async def get_stats(self, group_by: str | None) -> PackStatsDTO:
        """Return aggregated stats."""
        ...

    async def list_installations(
        self, pack_id: UUID, offset: int, limit: int
    ) -> PackInstallationPageDTO:
        """Return installations page."""
        ...


class TemplatePackWriter(Protocol):
    """Persist pack mutations."""

    async def create_pack(self, data: PackCreateDTO) -> PackDetailDTO:
        """Create local pack with assets."""
        ...

    async def install_pack(self, pack_id: UUID) -> PackInstallResultDTO:
        """Install pack (bulk create commands/scripts)."""
        ...

    async def uninstall_pack(self, pack_id: UUID) -> None:
        """Uninstall pack."""
        ...

    async def update_pack(self, pack_id: UUID) -> PackInstallResultDTO:
        """Update pack (uninstall+install)."""
        ...

    async def get_pack_view(self, pack_id: UUID) -> PackViewDTO | None:
        """Return view only."""
        ...
