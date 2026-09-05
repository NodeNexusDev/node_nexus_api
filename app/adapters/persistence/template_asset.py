"""SQLAlchemy adapter for template assets (2.0)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import tarfile
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.template_pack import PackAssetCreateDTO, PackAssetDTO
from app.models.template_asset import TemplateAssetModel

logger = structlog.get_logger(__name__)


class SqlAlchemyTemplateAssetGateway:
    """Persist assets via ``template_assets`` table and handle tar streaming."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write_assets(
        self, pack_id: uuid.UUID, assets: tuple[PackAssetCreateDTO, ...]
    ) -> tuple[PackAssetDTO, ...]:
        """Decode base64, compute size/sha and persist (TemplateAssetWriter)."""
        async with self._sessionmaker.begin() as session:
            result = await self.write_assets_in_session(session, pack_id, assets)
            return tuple(result)

    async def write_assets_in_session(
        self,
        session: AsyncSession,
        pack_id: uuid.UUID,
        assets: tuple[PackAssetCreateDTO, ...],
    ) -> tuple[PackAssetDTO, ...]:
        """Write assets within an existing session/transaction (atomic)."""
        now = datetime.now(UTC)
        result: list[PackAssetDTO] = []
        for asset in assets:
            try:
                raw = base64.b64decode(asset.content_base64, validate=True)
            except Exception as exc:
                from app.core.exceptions import DomainError

                raise DomainError(
                    f"Invalid base64 for asset {asset.path}: {exc}"
                ) from exc
            size = len(raw)
            sha = hashlib.sha256(raw).hexdigest()
            try:
                content_str = raw.decode("utf-8")
            except UnicodeDecodeError:
                content_str = base64.b64encode(raw).decode()
            model = TemplateAssetModel(
                id=uuid.uuid4(),
                pack_id=pack_id,
                path=asset.path,
                content=content_str,
                size=size,
                sha=sha,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            result.append(
                PackAssetDTO(
                    id=model.id,
                    pack_id=pack_id,
                    path=asset.path,
                    size=size,
                    sha=sha,
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.flush()
        return tuple(result)

    async def list_assets(self, pack_id: uuid.UUID) -> tuple[PackAssetDTO, ...]:
        """List persisted assets for a pack."""
        async with self._sessionmaker() as session:
            rows = await session.execute(
                select(TemplateAssetModel).where(TemplateAssetModel.pack_id == pack_id)
            )
            models = rows.scalars().all()
            return tuple(
                PackAssetDTO(
                    id=m.id,
                    pack_id=m.pack_id,
                    path=m.path,
                    size=m.size,
                    sha=m.sha,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                )
                for m in models
            )

    async def get_assets_tar(self, pack_id: uuid.UUID) -> bytes:
        """Stream assets as tar archive bytes."""
        async with self._sessionmaker() as session:
            rows = await session.execute(
                select(TemplateAssetModel).where(TemplateAssetModel.pack_id == pack_id)
            )
            models = rows.scalars().all()
            # Snapshot needed data to avoid holding session in thread
            snapshot = [
                (m.path, m.content, m.size, m.created_at.timestamp()) for m in models
            ]

        def _build() -> bytes:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for path, content, size, mtime in snapshot:
                    raw: bytes
                    try:
                        raw = content.encode("utf-8")
                        if size != len(raw):
                            try:
                                decoded = base64.b64decode(content, validate=True)
                                if len(decoded) == size:
                                    raw = decoded
                            except Exception as exc:
                                logger.debug(
                                    "template_asset.base64_fallback_failed",
                                    path=path,
                                    error=str(exc),
                                )
                    except Exception as exc:
                        logger.warning(
                            "template_asset.content_encode_failed",
                            path=path,
                            error=str(exc),
                        )
                        raw = b""
                    info = tarfile.TarInfo(name=path)
                    info.size = len(raw)
                    info.mtime = int(mtime)
                    info.mode = 0o644
                    tar.addfile(info, io.BytesIO(raw))
            buf.seek(0)
            return buf.getvalue()

        return await asyncio.to_thread(_build)
