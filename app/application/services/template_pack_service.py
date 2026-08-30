"""Template pack application service (in-memory stub with assets)."""

from __future__ import annotations

import base64
import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import structlog

from app.application.dto.template_pack import (
    PackAssetDTO,
    PackCreateDTO,
    PackDetailDTO,
    PackInstallationDTO,
    PackInstallationPageDTO,
    PackInstallItemDTO,
    PackInstallResultDTO,
    PackListQueryDTO,
    PackPageDTO,
    PackStatsBucketDTO,
    PackStatsDTO,
    PackViewDTO,
)
from app.core.exceptions import DomainError

audit = structlog.get_logger("audit")

# In-memory stores (process-local)
_PACKS: dict[uuid.UUID, PackDetailDTO] = {}
_INSTALLATIONS: dict[uuid.UUID, list[PackInstallationDTO]] = {}
# pack_id -> list of installations


class PackNotFoundError(DomainError):
    """Raised when pack not found."""


class PackConflictError(DomainError):
    """Raised when pack already installed."""


class TemplatePackService:
    """Manage template packs (stub, functional with assets)."""

    def __init__(self) -> None:
        self._packs = _PACKS
        self._installations = _INSTALLATIONS

    async def create_pack(self, data: PackCreateDTO) -> PackDetailDTO:
        """Create local pack with assets."""
        # Check duplicate pack_id per registry_id
        for existing in self._packs.values():
            if (
                existing.pack.registry_id == data.registry_id
                and existing.pack.pack_id == data.manifest.pack_id
            ):
                raise DomainError(
                    f"Pack {data.manifest.pack_id} already exists for registry"
                )
        now = datetime.now(UTC)
        pack_id = uuid.uuid4()
        view = PackViewDTO(
            id=pack_id,
            registry_id=data.registry_id,
            pack_id=data.manifest.pack_id,
            name=data.manifest.name,
            description=data.manifest.description,
            version=data.manifest.version,
            author=data.manifest.author,
            tags=tuple(data.manifest.tags),
            manifest_sha=data.manifest.manifest_sha,
            readme=data.readme,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        assets: list[PackAssetDTO] = []
        for asset in data.assets:
            try:
                raw = base64.b64decode(asset.content_base64, validate=True)
            except Exception as exc:
                raise DomainError(
                    f"Invalid base64 for asset {asset.path}: {exc}"
                ) from exc
            size = len(raw)
            sha = hashlib.sha256(raw).hexdigest()
            assets.append(
                PackAssetDTO(
                    id=uuid.uuid4(),
                    pack_id=pack_id,
                    path=asset.path,
                    size=size,
                    sha=sha,
                    created_at=now,
                    updated_at=now,
                )
            )
        detail = PackDetailDTO(
            pack=view,
            assets=tuple(assets),
            commands=tuple(data.commands),
            scripts=tuple(data.scripts),
        )
        self._packs[pack_id] = detail
        audit.info(
            "template_pack.create.ok",
            pack_id=str(pack_id),
            name=view.name,
            assets=len(assets),
        )
        return detail

    async def list_packs(self, query: PackListQueryDTO) -> PackPageDTO:
        """List with filters and offset pagination."""
        items = list(self._packs.values())
        # filter registry_id
        if query.registry_id is not None:
            items = [p for p in items if p.pack.registry_id == query.registry_id]
        # filter tag
        if query.tag is not None:
            items = [p for p in items if query.tag in (p.pack.tags or ())]
        # filter installed
        if query.installed is not None:
            if query.installed:
                items = [p for p in items if p.pack.installed_version is not None]
            else:
                items = [p for p in items if p.pack.installed_version is None]
        # filter search
        if query.search:
            term = query.search.lower()
            items = [
                p
                for p in items
                if term in p.pack.name.lower()
                or (p.pack.description and term in p.pack.description.lower())
            ]
        items.sort(key=lambda p: p.pack.created_at, reverse=True)
        total = len(items)
        sliced = items[query.offset : query.offset + query.limit]
        views = tuple(p.pack for p in sliced)
        return PackPageDTO(items=views, total=total)

    async def get_pack_detail(self, pack_id: uuid.UUID) -> PackDetailDTO:
        """Get detail with assets or raise."""
        detail = self._packs.get(pack_id)
        if detail is None:
            raise PackNotFoundError(f"Pack {pack_id} not found")
        return detail

    async def get_pack_view(self, pack_id: uuid.UUID) -> PackViewDTO:
        """Get view only."""
        detail = await self.get_pack_detail(pack_id)
        return detail.pack

    async def install_pack(self, pack_id: uuid.UUID) -> PackInstallResultDTO:
        """Install pack — bulk create commands/scripts with template_pack_id FK.

        Returns 201 on success, raises PackConflictError (409) if already installed,
        and returns 207 envelope when partially succeeded (simulated).
        """
        detail = self._packs.get(pack_id)
        if detail is None:
            raise PackNotFoundError(f"Pack {pack_id} not found")
        if detail.pack.installed_version is not None:
            raise PackConflictError(f"Pack {pack_id} already installed")
        # Simulate bulk create
        results: list[PackInstallItemDTO] = []
        # commands
        for cmd in detail.commands:
            name = "unknown"
            try:
                if isinstance(cmd, dict):
                    name = str(cmd.get("name", "command"))
                else:
                    # Pydantic model or object with name attr
                    name = str(getattr(cmd, "name", "command"))
                # Simulate failure if name contains "fail"
                if "fail" in name.lower():
                    raise RuntimeError(f"Failed to create command {name}")
                entity_id = uuid.uuid4()
                # Record installation
                results.append(
                    PackInstallItemDTO(
                        entity_type="command",
                        entity_id=entity_id,
                        name=name,
                        status="success",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    PackInstallItemDTO(
                        entity_type="command",
                        entity_id=None,
                        name=name,
                        status="error",
                        error=str(exc),
                    )
                )
        # scripts
        for scr in detail.scripts:
            name = "unknown"
            try:
                if isinstance(scr, dict):
                    name = str(scr.get("name", "script"))
                else:
                    name = str(getattr(scr, "name", "script"))
                if "fail" in name.lower():
                    raise RuntimeError(f"Failed to create script {name}")
                entity_id = uuid.uuid4()
                results.append(
                    PackInstallItemDTO(
                        entity_type="script",
                        entity_id=entity_id,
                        name=name,
                        status="success",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                results.append(
                    PackInstallItemDTO(
                        entity_type="script",
                        entity_id=None,
                        name=name,
                        status="error",
                        error=str(exc),
                    )
                )
        # If no commands/scripts defined, still succeed with empty
        succeeded = sum(1 for r in results if r.status == "success")
        failed = len(results) - succeeded
        # Persist installations for successes
        now = datetime.now(UTC)
        installations = self._installations.setdefault(pack_id, [])
        for item in results:
            if item.status == "success" and item.entity_id is not None:
                installations.append(
                    PackInstallationDTO(
                        id=uuid.uuid4(),
                        pack_id=pack_id,
                        entity_type=item.entity_type,
                        entity_id=item.entity_id,
                        created_at=now,
                    )
                )
        # Update pack installed info if at least one succeeded
        if succeeded > 0:
            updated_view = PackViewDTO(
                id=detail.pack.id,
                registry_id=detail.pack.registry_id,
                pack_id=detail.pack.pack_id,
                name=detail.pack.name,
                description=detail.pack.description,
                version=detail.pack.version,
                author=detail.pack.author,
                tags=detail.pack.tags,
                manifest_sha=detail.pack.manifest_sha,
                readme=detail.pack.readme,
                installed_version=detail.pack.version,
                installed_at=now,
                created_at=detail.pack.created_at,
                updated_at=now,
            )
            self._packs[pack_id] = PackDetailDTO(
                pack=updated_view,
                assets=detail.assets,
                commands=detail.commands,
                scripts=detail.scripts,
            )
        audit.info(
            "template_pack.install.ok",
            pack_id=str(pack_id),
            total=len(results),
            succeeded=succeeded,
            failed=failed,
        )
        return PackInstallResultDTO(
            pack_id=pack_id,
            version=detail.pack.version,
            total=len(results),
            succeeded=succeeded,
            failed=failed,
            results=tuple(results),
        )

    async def uninstall_pack(self, pack_id: uuid.UUID) -> None:
        """Uninstall — remove installations and reset installed_version."""
        detail = self._packs.get(pack_id)
        if detail is None:
            raise PackNotFoundError(f"Pack {pack_id} not found")
        # Clear installations
        self._installations.pop(pack_id, None)
        # Reset installed info
        if detail.pack.installed_version is not None:
            updated = PackViewDTO(
                id=detail.pack.id,
                registry_id=detail.pack.registry_id,
                pack_id=detail.pack.pack_id,
                name=detail.pack.name,
                description=detail.pack.description,
                version=detail.pack.version,
                author=detail.pack.author,
                tags=detail.pack.tags,
                manifest_sha=detail.pack.manifest_sha,
                readme=detail.pack.readme,
                installed_version=None,
                installed_at=None,
                created_at=detail.pack.created_at,
                updated_at=datetime.now(UTC),
            )
            self._packs[pack_id] = PackDetailDTO(
                pack=updated,
                assets=detail.assets,
                commands=detail.commands,
                scripts=detail.scripts,
            )
        audit.info("template_pack.uninstall.ok", pack_id=str(pack_id))

    async def update_pack(self, pack_id: uuid.UUID) -> PackInstallResultDTO:
        """Update — uninstall then install."""
        detail = self._packs.get(pack_id)
        if detail is None:
            raise PackNotFoundError(f"Pack {pack_id} not found")
        # uninstall (ignore if not installed)
        if pack_id in self._installations:
            await self.uninstall_pack(pack_id)
        # install again
        return await self.install_pack(pack_id)

    async def list_installations(
        self, pack_id: uuid.UUID, offset: int, limit: int
    ) -> PackInstallationPageDTO:
        """List installations with offset pagination."""
        if pack_id not in self._packs:
            raise PackNotFoundError(f"Pack {pack_id} not found")
        all_items = self._installations.get(pack_id, [])
        # sort by created_at desc
        sorted_items = sorted(all_items, key=lambda i: i.created_at, reverse=True)
        total = len(sorted_items)
        sliced = tuple(sorted_items[offset : offset + limit])
        return PackInstallationPageDTO(items=sliced, total=total)

    async def get_stats(self, group_by: str | None) -> PackStatsDTO:
        """Get stats with optional group_by."""
        all_packs = list(self._packs.values())
        total = len(all_packs)
        installed = sum(1 for p in all_packs if p.pack.installed_version is not None)
        not_installed = total - installed
        buckets: list[PackStatsBucketDTO] = []
        if group_by:
            if group_by == "registry_id":
                groups: dict[str, list[PackDetailDTO]] = defaultdict(list)
                for p in all_packs:
                    key = str(p.pack.registry_id) if p.pack.registry_id else "local"
                    groups[key].append(p)
                for key, packs in groups.items():
                    inst = sum(1 for x in packs if x.pack.installed_version)
                    buckets.append(
                        PackStatsBucketDTO(
                            group=key,
                            total=len(packs),
                            installed=inst,
                            not_installed=len(packs) - inst,
                        )
                    )
            elif group_by == "tag":
                groups_tag: dict[str, list[PackDetailDTO]] = defaultdict(list)
                for p in all_packs:
                    if p.pack.tags:
                        for tag in p.pack.tags:
                            groups_tag[tag].append(p)
                    else:
                        groups_tag["untagged"].append(p)
                for key, packs in groups_tag.items():
                    inst = sum(1 for x in packs if x.pack.installed_version)
                    buckets.append(
                        PackStatsBucketDTO(
                            group=key,
                            total=len(packs),
                            installed=inst,
                            not_installed=len(packs) - inst,
                        )
                    )
            elif group_by == "installed":
                buckets.append(
                    PackStatsBucketDTO(
                        group="installed",
                        total=installed,
                        installed=installed,
                        not_installed=0,
                    )
                )
                buckets.append(
                    PackStatsBucketDTO(
                        group="not_installed",
                        total=not_installed,
                        installed=0,
                        not_installed=not_installed,
                    )
                )
            elif group_by == "version":
                groups_ver: dict[str, list[PackDetailDTO]] = defaultdict(list)
                for p in all_packs:
                    groups_ver[p.pack.version].append(p)
                for key, packs in groups_ver.items():
                    inst = sum(1 for x in packs if x.pack.installed_version)
                    buckets.append(
                        PackStatsBucketDTO(
                            group=key,
                            total=len(packs),
                            installed=inst,
                            not_installed=len(packs) - inst,
                        )
                    )
            else:
                # generic: single bucket per group_by value as string
                buckets.append(
                    PackStatsBucketDTO(
                        group=group_by,
                        total=total,
                        installed=installed,
                        not_installed=not_installed,
                    )
                )
        return PackStatsDTO(
            total=total,
            installed=installed,
            not_installed=not_installed,
            buckets=tuple(buckets),
        )
