"""SQLAlchemy gateway for compose projects."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.compose import (
    ComposeCreateDTO,
    ComposeUpdateDTO,
    ComposeViewDTO,
)
from app.core.exceptions import ComposeProjectAlreadyExistsError
from app.models.compose_project import ComposeProjectModel


def _to_dto(model: ComposeProjectModel) -> ComposeViewDTO:
    """Map ORM model to application DTO."""
    return ComposeViewDTO(
        id=UUID(str(model.id)),
        node_id=UUID(str(model.node_id)),
        project_name=str(model.project_name),
        compose=str(model.compose),
        env=dict(model.env) if isinstance(model.env, dict) else None,
        template_pack_id=UUID(str(model.template_pack_id))
        if model.template_pack_id is not None
        else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyComposeGateway:
    """Short-scope gateway for compose persistence."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get_project(
        self, node_id: UUID, project_name: str
    ) -> ComposeViewDTO | None:
        """Return one compose project."""
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ComposeProjectModel).where(
                    ComposeProjectModel.node_id == node_id,
                    ComposeProjectModel.project_name == project_name,
                )
            )
            model = result.scalar_one_or_none()
            return _to_dto(model) if model is not None else None

    async def list_projects(
        self, node_id: UUID, offset: int, limit: int
    ) -> list[ComposeViewDTO]:
        """Return a page ordered by created_at desc."""
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(ComposeProjectModel)
                .where(ComposeProjectModel.node_id == node_id)
                .order_by(
                    ComposeProjectModel.created_at.desc(),
                    ComposeProjectModel.id.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
            models = list(result.scalars().all())
            return [_to_dto(m) for m in models]

    async def count_projects(self, node_id: UUID) -> int:
        """Return total count for node."""
        async with self._sessionmaker() as session:
            result = await session.execute(
                select(func.count())
                .select_from(ComposeProjectModel)
                .where(ComposeProjectModel.node_id == node_id)
            )
            return int(result.scalar_one())

    async def stats(self, node_id: UUID) -> int:
        """Alias for count_projects."""
        return await self.count_projects(node_id)

    async def create_project(self, data: ComposeCreateDTO) -> ComposeViewDTO:
        """Create a compose project, handling unique violation."""
        try:
            async with self._sessionmaker.begin() as session:
                model = ComposeProjectModel(
                    id=uuid.uuid4(),
                    node_id=data.node_id,
                    project_name=data.project_name,
                    compose=data.compose,
                    env=dict(data.env) if data.env else None,
                    template_pack_id=data.template_pack_id,
                )
                session.add(model)
                await session.flush()
                # refresh to load defaults
                await session.refresh(model)
                return _to_dto(model)
        except IntegrityError as exc:
            raise ComposeProjectAlreadyExistsError(
                f"Project {data.project_name!r} already exists for node {data.node_id}"
            ) from exc

    async def update_project(
        self, node_id: UUID, project_name: str, data: ComposeUpdateDTO
    ) -> ComposeViewDTO | None:
        """Update a compose project."""
        async with self._sessionmaker.begin() as session:
            result = await session.execute(
                select(ComposeProjectModel).where(
                    ComposeProjectModel.node_id == node_id,
                    ComposeProjectModel.project_name == project_name,
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            if data.compose is not None:
                model.compose = data.compose  # type: ignore[assignment]
            if data.has_env:
                if data.env is not None:
                    model.env = dict(data.env)  # type: ignore[assignment]
                else:
                    model.env = None  # type: ignore[assignment]
            if data.has_template_pack_id:
                model.template_pack_id = data.template_pack_id  # type: ignore[assignment]
            await session.flush()
            await session.refresh(model)
            return _to_dto(model)

    async def delete_project(self, node_id: UUID, project_name: str) -> bool:
        """Delete a compose project."""
        async with self._sessionmaker.begin() as session:
            result = await session.execute(
                select(ComposeProjectModel).where(
                    ComposeProjectModel.node_id == node_id,
                    ComposeProjectModel.project_name == project_name,
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                return False
            await session.delete(model)
            await session.flush()
            return True

    async def upsert_project(self, data: ComposeCreateDTO) -> ComposeViewDTO:
        """Create or update a compose project."""
        existing = await self.get_project(data.node_id, data.project_name)
        if existing is None:
            return await self.create_project(data)
        dto = ComposeUpdateDTO(
            compose=data.compose,
            env=data.env,
            has_env=True,
            template_pack_id=data.template_pack_id,
            has_template_pack_id=True,
        )
        updated = await self.update_project(data.node_id, data.project_name, dto)
        # update_project returns None only if raced delete, fallback to create
        if updated is None:
            return await self.create_project(data)
        return updated
