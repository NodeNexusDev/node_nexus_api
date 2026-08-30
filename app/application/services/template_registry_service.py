"""Template registry application service (in-memory stub)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from app.application.dto.template_registry import (
    RegistryCreateDTO,
    RegistryPageDTO,
    RegistrySyncResultDTO,
    RegistryViewDTO,
)
from app.core.exceptions import DomainError

audit = structlog.get_logger("audit")

# In-memory store for stub (process-local)
_REGISTRIES: dict[uuid.UUID, RegistryViewDTO] = {}


class RegistryNotFoundError(DomainError):
    """Raised when registry not found."""


class RegistryConflictError(DomainError):
    """Raised when registry already exists."""


class TemplateRegistryService:
    """Manage template registries (stub, functional)."""

    def __init__(self) -> None:
        self._store = _REGISTRIES

    async def create_registry(self, data: RegistryCreateDTO) -> RegistryViewDTO:
        """Create a registry (409 on duplicate owner/name)."""
        for existing in self._store.values():
            if existing.owner == data.owner and existing.name == data.name:
                raise RegistryConflictError(
                    f"Registry {data.owner}/{data.name} already exists"
                )
        now = datetime.now(UTC)
        view = RegistryViewDTO(
            id=uuid.uuid4(),
            owner=data.owner,
            name=data.name,
            default_branch=data.default_branch or "main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        self._store[view.id] = view
        audit.info(
            "template_registry.create.ok",
            registry_id=str(view.id),
            owner=data.owner,
            name=data.name,
        )
        return view

    async def list_registries(self, offset: int, limit: int) -> RegistryPageDTO:
        """List with offset pagination."""
        items = sorted(self._store.values(), key=lambda r: r.created_at, reverse=True)
        total = len(items)
        page = tuple(items[offset : offset + limit])
        return RegistryPageDTO(items=page, total=total)

    async def get_registry(self, registry_id: uuid.UUID) -> RegistryViewDTO:
        """Get one or raise."""
        view = self._store.get(registry_id)
        if view is None:
            raise RegistryNotFoundError(f"Registry {registry_id} not found")
        return view

    async def delete_registry(self, registry_id: uuid.UUID) -> None:
        """Delete or raise."""
        if registry_id not in self._store:
            raise RegistryNotFoundError(f"Registry {registry_id} not found")
        del self._store[registry_id]
        audit.info("template_registry.delete.ok", registry_id=str(registry_id))

    async def sync_registry(self, registry_id: uuid.UUID) -> RegistrySyncResultDTO:
        """Sync stub — returns empty success."""
        view = self._store.get(registry_id)
        if view is None:
            raise RegistryNotFoundError(f"Registry {registry_id} not found")
        now = datetime.now(UTC)
        updated = RegistryViewDTO(
            id=view.id,
            owner=view.owner,
            name=view.name,
            default_branch=view.default_branch,
            last_synced_at=now,
            created_at=view.created_at,
            updated_at=now,
        )
        self._store[registry_id] = updated
        # Dummy sync: no packs discovered yet
        result = RegistrySyncResultDTO(
            registry_id=registry_id,
            total=0,
            succeeded=0,
            failed=0,
            results=(),
        )
        audit.info("template_registry.sync.ok", registry_id=str(registry_id))
        return result
