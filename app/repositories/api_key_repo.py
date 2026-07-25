"""API key repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKeyModel
from app.schemas.api_key import APIKeyResponse


class APIKeyRepository:
    """Repository for API key CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        key_hash: str,
        key_prefix: str,
        scope: str = "read-write",
    ) -> APIKeyModel:
        model = APIKeyModel(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scope=scope,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_by_key_hash(self, key_hash: str) -> APIKeyModel | None:
        result = await self._session.execute(
            select(APIKeyModel).where(APIKeyModel.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, key_id: uuid.UUID) -> APIKeyModel | None:
        result = await self._session.execute(
            select(APIKeyModel).where(APIKeyModel.id == key_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self, offset: int = 0, limit: int = 100
    ) -> tuple[list[APIKeyResponse], int]:
        count_result = await self._session.execute(
            select(func.count()).select_from(APIKeyModel)
        )
        total = count_result.scalar_one()

        result = await self._session.execute(
            select(APIKeyModel)
            .order_by(APIKeyModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = [APIKeyResponse.model_validate(m) for m in result.scalars().all()]
        return items, total

    async def update(self, key_id: uuid.UUID, data: dict) -> APIKeyModel | None:
        result = await self._session.execute(
            select(APIKeyModel).where(APIKeyModel.id == key_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        for field, value in data.items():
            setattr(model, field, value)
        await self._session.flush()
        return model

    async def revoke(self, key_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(APIKeyModel).where(APIKeyModel.id == key_id)
        )
        model = result.scalar_one()
        model.is_active = False
        await self._session.flush()

    async def update_last_used(self, key_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(APIKeyModel).where(APIKeyModel.id == key_id)
        )
        model = result.scalar_one()
        model.last_used_at = datetime.now(UTC)
        await self._session.flush()
