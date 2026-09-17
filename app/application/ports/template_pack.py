"""Template pack persistence ports."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from app.application.dto.template_pack import (
    PackAssetCreateDTO,
    PackAssetDTO,
    PackCreateDTO,
    PackDetailDTO,
    PackInstallationPageDTO,
    PackInstallResultDTO,
    PackListQueryDTO,
    PackPageDTO,
    PackStatsDTO,
    PackUpdateDTO,
    PackViewDTO,
    SyncedPackDTO,
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

    async def get_assets_tar(self, pack_id: UUID) -> bytes:
        """Return tar archive bytes for pack assets."""
        ...


class TemplatePackWriter(Protocol):
    """Persist pack mutations."""

    async def create_pack(self, data: PackCreateDTO) -> PackDetailDTO:
        """Create local pack with assets."""
        ...

    async def install_pack(
        self,
        pack_id: UUID,
        on_conflict: Literal["fail", "rename"] = "fail",
    ) -> PackInstallResultDTO:
        """Install pack (bulk create commands/scripts with FK)."""
        ...

    async def uninstall_pack(self, pack_id: UUID) -> None:
        """Uninstall pack."""
        ...

    async def update_pack(
        self,
        pack_id: UUID,
        on_conflict: Literal["fail", "rename"] = "fail",
    ) -> PackInstallResultDTO:
        """Update pack (uninstall+install)."""
        ...

    async def patch_pack(self, pack_id: UUID, data: PackUpdateDTO) -> PackViewDTO:
        """Update pack metadata (partial)."""
        ...

    async def delete_pack(self, pack_id: UUID) -> None:
        """Hard delete pack with assets, installations and created rows."""
        ...

    async def upsert_synced_pack(self, data: SyncedPackDTO) -> tuple[UUID, str]:
        """Create or update a pack from registry sync.

        Returns ``(pack_id, outcome)`` with outcome ``created``,
        ``updated`` or ``unchanged``.
        """
        ...


class TemplatePackGateway(TemplatePackReader, TemplatePackWriter, Protocol):
    """Full pack persistence port."""


class TemplateAssetWriter(Protocol):
    """Persist template pack assets (2.0)."""

    async def write_assets(
        self, pack_id: UUID, assets: tuple[PackAssetCreateDTO, ...]
    ) -> tuple[PackAssetDTO, ...]:
        """Decode base64, compute size/sha and persist assets."""
        ...

    async def list_assets(self, pack_id: UUID) -> tuple[PackAssetDTO, ...]:
        """List persisted assets for a pack."""
        ...

    async def get_assets_tar(self, pack_id: UUID) -> bytes:
        """Stream assets as tar archive bytes."""
        ...
