"""Template pack application service (DB-backed via gateway)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Literal

import structlog

from app.application.dto.template_pack import (
    PackCreateDTO,
    PackDetailDTO,
    PackInstallationPageDTO,
    PackInstallResultDTO,
    PackListQueryDTO,
    PackPageDTO,
    PackStatsDTO,
    PackUpdateDTO,
    PackViewDTO,
)
from app.application.ports.template_pack import TemplatePackGateway
from app.core.exceptions import PackConflictError, PackNotFoundError

audit = structlog.get_logger("audit")

# Re-exported for handlers importing error types from the service module.
__all__ = [
    "PackConflictError",
    "PackNotFoundError",
    "TemplatePackService",
]

_TAR_CHUNK_SIZE = 65_536


class TemplatePackService:
    """Manage template packs persisted in the database.

    Thin orchestrator over the persistence port:
    all state transitions run inside gateway transactions.
    """

    def __init__(self, gateway: TemplatePackGateway) -> None:
        self._gateway = gateway

    async def create_pack(self, data: PackCreateDTO) -> PackDetailDTO:
        """Create local pack with content and assets."""
        detail = await self._gateway.create_pack(data)
        audit.info(
            "template_pack.create.ok",
            pack_id=str(detail.pack.id),
            name=detail.pack.name,
            assets=len(detail.assets),
        )
        return detail

    async def list_packs(self, query: PackListQueryDTO) -> PackPageDTO:
        """List with filters and offset pagination."""
        return await self._gateway.list_packs(query)

    async def get_pack_detail(self, pack_id: uuid.UUID) -> PackDetailDTO:
        """Get detail with assets or raise."""
        detail = await self._gateway.get_pack(pack_id)
        if detail is None:
            raise PackNotFoundError(f"Pack {pack_id} not found")
        return detail

    async def get_pack_view(self, pack_id: uuid.UUID) -> PackViewDTO:
        """Get view only."""
        detail = await self.get_pack_detail(pack_id)
        return detail.pack

    async def get_assets_tar(self, pack_id: uuid.UUID) -> bytes:
        """Return tar archive bytes for pack assets (for streaming)."""
        return await self._gateway.get_assets_tar(pack_id)

    async def stream_assets_tar(self, pack_id: uuid.UUID) -> bytes:
        """Alias for get_assets_tar (streaming compat)."""
        return await self.get_assets_tar(pack_id)

    async def iterate_assets_tar(
        self, pack_id: uuid.UUID, chunk_size: int = _TAR_CHUNK_SIZE
    ) -> AsyncIterator[bytes]:
        """Yield tar archive in chunks for StreamingResponse."""
        data = await self.get_assets_tar(pack_id)
        for offset in range(0, len(data), chunk_size):
            yield data[offset : offset + chunk_size]

    async def install_pack(
        self,
        pack_id: uuid.UUID,
        on_conflict: Literal["fail", "rename"] = "fail",
    ) -> PackInstallResultDTO:
        """Install pack — materialize content as commands/scripts.

        Single-transaction write; name conflicts in ``fail`` mode raise
        409 before anything is persisted. ``installed_version`` is set
        only when at least one row was created.
        """
        result = await self._gateway.install_pack(pack_id, on_conflict=on_conflict)
        audit.info(
            "template_pack.install.ok",
            pack_id=str(pack_id),
            total=result.total,
            succeeded=result.succeeded,
            failed=result.failed,
            on_conflict=on_conflict,
        )
        return result

    async def uninstall_pack(self, pack_id: uuid.UUID) -> None:
        """Uninstall — remove created rows and reset installed_version."""
        await self._gateway.uninstall_pack(pack_id)
        audit.info("template_pack.uninstall.ok", pack_id=str(pack_id))

    async def update_pack(
        self,
        pack_id: uuid.UUID,
        on_conflict: Literal["fail", "rename"] = "fail",
    ) -> PackInstallResultDTO:
        """Reinstall current content in one transaction.

        A 409 is still possible when an unrelated row owns a colliding
        name (fail mode) — the pack is then left uninstalled.
        """
        return await self._gateway.update_pack(pack_id, on_conflict=on_conflict)

    async def list_installations(
        self, pack_id: uuid.UUID, offset: int, limit: int
    ) -> PackInstallationPageDTO:
        """List installations with offset pagination."""
        return await self._gateway.list_installations(pack_id, offset, limit)

    async def get_stats(self, group_by: str | None) -> PackStatsDTO:
        """Get stats with optional group_by."""
        return await self._gateway.get_stats(group_by)

    async def patch_pack(self, pack_id: uuid.UUID, data: PackUpdateDTO) -> PackViewDTO:
        """Update pack metadata (partial)."""
        view = await self._gateway.patch_pack(pack_id, data)
        audit.info("template_pack.update.ok", pack_id=str(pack_id))
        return view

    async def delete_pack(self, pack_id: uuid.UUID) -> None:
        """Hard delete pack with assets, installations and created rows."""
        await self._gateway.delete_pack(pack_id)
        audit.info("template_pack.delete.ok", pack_id=str(pack_id))
