"""Short-scope SQLAlchemy adapter for API-key persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.api_key import (
    APIKeyAuthDTO,
    APIKeyPageDTO,
    APIKeyPersistenceDTO,
    APIKeyUpdateDTO,
    APIKeyViewDTO,
)
from app.models.api_key import APIKeyModel


class SqlAlchemyAPIKeyGateway:
    """Implement authentication and management persistence ports."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_auth_by_hash(self, key_hash: str) -> APIKeyAuthDTO | None:
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(APIKeyModel).where(APIKeyModel.key_hash == key_hash)
            )
            model = result.scalar_one_or_none()
            return self._to_auth(model) if model is not None else None

    async def get_api_key(self, key_id: UUID) -> APIKeyViewDTO | None:
        async with self._sessionmaker() as session:
            model = await self._get_model(session, key_id)
            return self._to_view(model) if model is not None else None

    async def list_api_keys(self, offset: int, limit: int) -> APIKeyPageDTO:
        async with self._sessionmaker() as session:
            count_result = await session.execute(
                select(func.count()).select_from(APIKeyModel)
            )
            result = await session.execute(
                select(APIKeyModel)
                .order_by(APIKeyModel.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return APIKeyPageDTO(
                items=tuple(self._to_view(model) for model in result.scalars()),
                total=count_result.scalar_one(),
            )

    async def create_api_key(self, data: APIKeyPersistenceDTO) -> APIKeyViewDTO:
        async with self._sessionmaker.begin() as session:
            model = APIKeyModel(
                name=data.name,
                key_hash=data.key_hash,
                key_prefix=data.key_prefix,
                scope=data.scope,
            )
            session.add(model)
            await session.flush()
            return self._to_view(model)

    async def update_api_key(
        self, key_id: UUID, data: APIKeyUpdateDTO
    ) -> APIKeyViewDTO | None:
        async with self._sessionmaker.begin() as session:
            model = await self._get_model(session, key_id)
            if model is None:
                return None
            for field, value in data.changes:
                setattr(model, field, value)
            await session.flush()
            return self._to_view(model)

    async def revoke_api_key(self, key_id: UUID) -> bool:
        async with self._sessionmaker.begin() as session:
            model = await self._get_model(session, key_id)
            if model is None:
                return False
            model.is_active = False
            await session.flush()
            return True

    async def touch_last_used(self, key_id: UUID, used_at: datetime) -> None:
        async with self._sessionmaker.begin() as session:
            await session.execute(
                update(APIKeyModel)
                .where(APIKeyModel.id == key_id)
                .values(last_used_at=used_at)
            )

    @staticmethod
    async def _get_model(session: AsyncSession, key_id: UUID) -> APIKeyModel | None:
        result = await session.execute(
            select(APIKeyModel).where(APIKeyModel.id == key_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _to_auth(model: APIKeyModel) -> APIKeyAuthDTO:
        return APIKeyAuthDTO(
            id=model.id,
            key_prefix=model.key_prefix,
            is_active=model.is_active,
            scope=model.scope,
            expires_at=model.expires_at,
            last_used_at=model.last_used_at,
        )

    @staticmethod
    def _to_view(model: APIKeyModel) -> APIKeyViewDTO:
        return APIKeyViewDTO(
            id=model.id,
            name=model.name,
            key_prefix=model.key_prefix,
            is_active=model.is_active,
            scope=model.scope,
            created_at=model.created_at,
            last_used_at=model.last_used_at,
            expires_at=model.expires_at,
        )
