"""Template asset persistence ports (2.0)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.application.dto.template_pack import PackAssetCreateDTO, PackAssetDTO


class TemplateAssetWriter(Protocol):
    """Persist template pack assets."""

    async def write_assets(
        self, pack_id: UUID, assets: tuple[PackAssetCreateDTO, ...]
    ) -> tuple[PackAssetDTO, ...]:
        """Decode base64, compute size/sha and persist assets."""
        ...

    async def list_assets(self, pack_id: UUID) -> tuple[PackAssetDTO, ...]:
        """List persisted assets for a pack."""
        ...

    async def get_assets_tar(self, pack_id: UUID) -> bytes:
        """Return tar archive bytes for assets."""
        ...


class TemplateAssetReader(Protocol):
    """Read template pack assets."""

    async def list_assets(self, pack_id: UUID) -> tuple[PackAssetDTO, ...]:
        """List assets."""
        ...

    async def get_asset_content(self, pack_id: UUID, path: str) -> bytes | None:
        """Return raw asset bytes."""
        ...
