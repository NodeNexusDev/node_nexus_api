"""SQLAlchemy adapter for template registries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import override

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.template_registry import (
    RegistryCreateDTO,
    RegistryPageDTO,
    RegistryUpdateDTO,
    RegistryViewDTO,
)
from app.application.ports.credential_cipher import CredentialCipher
from app.application.ports.template_registry import TemplateRegistryGateway
from app.core.exceptions import (
    RegistryConflictError,
    RegistryNotFoundError,
)
from app.models.template_registry import TemplateRegistryModel

audit = structlog.get_logger()


class SqlAlchemyTemplateRegistryGateway(TemplateRegistryGateway):
    """Persist registries; GitHub tokens stored encrypted."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: CredentialCipher,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher

    @staticmethod
    def _view_of(model: TemplateRegistryModel) -> RegistryViewDTO:
        return RegistryViewDTO(
            id=model.id,
            owner=model.owner,
            name=model.name,
            default_branch=model.default_branch,
            last_synced_at=model.last_synced_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @override
    async def create_registry(self, data: RegistryCreateDTO) -> RegistryViewDTO:
        """Create a registry (409 on duplicate owner/name)."""
        now = datetime.now(UTC)
        async with self._sessionmaker.begin() as session:
            existing = await session.execute(
                select(TemplateRegistryModel.id).where(
                    TemplateRegistryModel.owner == data.owner,
                    TemplateRegistryModel.name == data.name,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise RegistryConflictError(
                    f"Registry {data.owner}/{data.name} already exists"
                )
            model = TemplateRegistryModel(
                id=uuid.uuid4(),
                owner=data.owner,
                name=data.name,
                github_token_encrypted=self._cipher.encrypt(data.github_token)
                if data.github_token
                else None,
                default_branch=data.default_branch or "main",
                last_synced_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            await session.flush()
            view = self._view_of(model)
        audit.info(
            "template_registry.create.ok",
            registry_id=str(view.id),
            owner=data.owner,
            name=data.name,
        )
        return view

    @override
    async def list_registries(self, offset: int, limit: int) -> RegistryPageDTO:
        """List with offset pagination."""
        offset = max(offset, 0)
        limit = min(max(limit, 1), 100)
        async with self._sessionmaker() as session:
            total = (
                await session.execute(
                    select(func.count()).select_from(TemplateRegistryModel)
                )
            ).scalar_one()
            rows = await session.execute(
                select(TemplateRegistryModel)
                .order_by(TemplateRegistryModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            items = tuple(self._view_of(m) for m in rows.scalars().all())
            return RegistryPageDTO(items=items, total=int(total))

    @override
    async def get_registry(self, registry_id: uuid.UUID) -> RegistryViewDTO | None:
        async with self._sessionmaker() as session:
            model = await session.get(TemplateRegistryModel, registry_id)
            if model is None:
                return None
            return self._view_of(model)

    @override
    async def get_registry_token(self, registry_id: uuid.UUID) -> str | None:
        """Return the decrypted GitHub token for sync (internal use)."""
        async with self._sessionmaker() as session:
            model = await session.get(TemplateRegistryModel, registry_id)
            if model is None:
                raise RegistryNotFoundError(f"Registry {registry_id} not found")
            return self._cipher.decrypt(model.github_token_encrypted)

    @override
    async def delete_registry(self, registry_id: uuid.UUID) -> None:
        """Delete; packs keep their rows with registry_id SET NULL."""
        async with self._sessionmaker.begin() as session:
            model = await session.get(TemplateRegistryModel, registry_id)
            if model is None:
                raise RegistryNotFoundError(f"Registry {registry_id} not found")
            await session.delete(model)
        audit.info("template_registry.delete.ok", registry_id=str(registry_id))

    @override
    async def patch_registry(
        self, registry_id: uuid.UUID, data: RegistryUpdateDTO
    ) -> RegistryViewDTO:
        """Partial update (owner/name/branch/token)."""
        async with self._sessionmaker.begin() as session:
            model = await session.get(TemplateRegistryModel, registry_id)
            if model is None:
                raise RegistryNotFoundError(f"Registry {registry_id} not found")
            new_owner = data.owner if data.owner is not None else model.owner
            new_name = data.name if data.name is not None else model.name
            if new_owner != model.owner or new_name != model.name:
                clash = await session.execute(
                    select(TemplateRegistryModel.id).where(
                        TemplateRegistryModel.owner == new_owner,
                        TemplateRegistryModel.name == new_name,
                        TemplateRegistryModel.id != registry_id,
                    )
                )
                if clash.scalar_one_or_none() is not None:
                    raise RegistryConflictError(
                        f"Registry {new_owner}/{new_name} already exists"
                    )
                model.owner = new_owner
                model.name = new_name
            if data.default_branch is not None:
                model.default_branch = data.default_branch
            if data.github_token is not None:
                model.github_token_encrypted = (
                    self._cipher.encrypt(data.github_token)
                    if data.github_token
                    else None
                )
            model.updated_at = datetime.now(UTC)
            await session.flush()
            return self._view_of(model)

    @override
    async def touch_synced(self, registry_id: uuid.UUID) -> RegistryViewDTO:
        """Mark registry synced now."""
        async with self._sessionmaker.begin() as session:
            model = await session.get(TemplateRegistryModel, registry_id)
            if model is None:
                raise RegistryNotFoundError(f"Registry {registry_id} not found")
            now = datetime.now(UTC)
            model.last_synced_at = now
            model.updated_at = now
            await session.flush()
            return self._view_of(model)
