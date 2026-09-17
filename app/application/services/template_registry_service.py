"""Template registry application service (DB-backed via gateway)."""

from __future__ import annotations

import base64
import uuid

import structlog

from app.application.dto.template_pack import PackAssetCreateDTO, SyncedPackDTO
from app.application.dto.template_registry import (
    RegistryCreateDTO,
    RegistryPageDTO,
    RegistrySyncItemDTO,
    RegistrySyncResultDTO,
    RegistryUpdateDTO,
    RegistryViewDTO,
)
from app.application.ports.template_pack import TemplatePackGateway
from app.application.ports.template_registry import TemplateRegistryGateway
from app.application.ports.template_source import FetchedPack, TemplateSource
from app.core.error_sanitize import sanitize_bulk_error
from app.core.exceptions import (
    DomainError,
    RegistryConflictError,
    RegistryNotFoundError,
)

audit = structlog.get_logger("audit")

# Re-exported for handlers importing error types from the service module.
__all__ = [
    "RegistryConflictError",
    "RegistryNotFoundError",
    "TemplateRegistryService",
]


class TemplateRegistryService:
    """Manage template registries persisted in the database."""

    def __init__(
        self,
        gateway: TemplateRegistryGateway,
        pack_gateway: TemplatePackGateway,
        source: TemplateSource | None = None,
    ) -> None:
        self._gateway = gateway
        self._packs = pack_gateway
        self._source = source

    async def create_registry(self, data: RegistryCreateDTO) -> RegistryViewDTO:
        """Create a registry (409 on duplicate owner/name)."""
        return await self._gateway.create_registry(data)

    async def list_registries(self, offset: int, limit: int) -> RegistryPageDTO:
        """List with offset pagination."""
        return await self._gateway.list_registries(offset, limit)

    async def get_registry(self, registry_id: uuid.UUID) -> RegistryViewDTO:
        """Get one or raise."""
        view = await self._gateway.get_registry(registry_id)
        if view is None:
            raise RegistryNotFoundError(f"Registry {registry_id} not found")
        return view

    async def delete_registry(self, registry_id: uuid.UUID) -> None:
        """Delete; packs keep their rows with registry_id SET NULL."""
        await self._gateway.delete_registry(registry_id)

    async def patch_registry(
        self, registry_id: uuid.UUID, data: RegistryUpdateDTO
    ) -> RegistryViewDTO:
        """Partial update (owner/name/branch/token)."""
        return await self._gateway.patch_registry(registry_id, data)

    async def sync_registry(self, registry_id: uuid.UUID) -> RegistrySyncResultDTO:
        """Fetch pack trees from GitHub and upsert packs.

        Unchanged packs (manifest_sha match) are skipped. Per-pack
        failures are collected as error items without rolling back
        successful upserts.
        """
        view = await self.get_registry(registry_id)
        token = await self._gateway.get_registry_token(registry_id)
        if self._source is None:
            raise DomainError("Registry sync source is not configured")
        try:
            fetched = await self._source.fetch_packs(
                view.owner, view.name, view.default_branch, token
            )
        except DomainError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DomainError(f"Registry sync failed: {exc}") from exc

        results: list[RegistrySyncItemDTO] = []
        succeeded = 0
        for pack in fetched:
            try:
                _pack_id, outcome = await self._upsert_fetched_pack(registry_id, pack)
                succeeded += 1
                results.append(
                    RegistrySyncItemDTO(
                        pack_id=pack.dirname,
                        status="success",
                        message=outcome,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    RegistrySyncItemDTO(
                        pack_id=pack.dirname,
                        status="error",
                        error=sanitize_bulk_error(exc),
                    )
                )
        await self._gateway.touch_synced(registry_id)
        audit.info(
            "template_registry.sync.ok",
            registry_id=str(registry_id),
            total=len(fetched),
            succeeded=succeeded,
            failed=len(fetched) - succeeded,
        )
        return RegistrySyncResultDTO(
            registry_id=registry_id,
            total=len(fetched),
            succeeded=succeeded,
            failed=len(fetched) - succeeded,
            results=tuple(results),
        )

    async def _upsert_fetched_pack(
        self, registry_id: uuid.UUID, pack: FetchedPack
    ) -> tuple[uuid.UUID, str]:
        """Validate a fetched pack and upsert it via the pack gateway."""
        manifest = pack.manifest
        pack_id = str(manifest.get("pack_id") or pack.dirname)
        name = manifest.get("name")
        version = manifest.get("version")
        if not isinstance(name, str) or not name:
            raise DomainError(f"Pack {pack.dirname}: manifest missing name")
        if not isinstance(version, str) or not version:
            raise DomainError(f"Pack {pack.dirname}: manifest missing version")
        tags = manifest.get("tags") or []
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise DomainError(f"Pack {pack.dirname}: manifest tags must be strings")
        description = manifest.get("description")
        author = manifest.get("author")
        if not isinstance(pack.commands, list) or not isinstance(pack.scripts, list):
            raise DomainError(f"Pack {pack.dirname}: commands/scripts must be lists")
        assets = tuple(
            PackAssetCreateDTO(
                path=a.path,
                content_base64=base64.b64encode(a.content).decode(),
            )
            for a in pack.assets
        )
        manifest_sha = pack.manifest_sha
        if manifest_sha is None:
            raw_sha = manifest.get("manifest_sha")
            manifest_sha = raw_sha if isinstance(raw_sha, str) else None
        return await self._packs.upsert_synced_pack(
            SyncedPackDTO(
                registry_id=registry_id,
                pack_id=pack_id,
                name=name,
                version=version,
                description=description if isinstance(description, str) else None,
                author=author if isinstance(author, str) else None,
                tags=tuple(tags),
                manifest_sha=manifest_sha,
                readme=pack.readme,
                commands=tuple(dict(c) for c in pack.commands if isinstance(c, dict)),
                scripts=tuple(dict(s) for s in pack.scripts if isinstance(s, dict)),
                assets=assets,
            )
        )
