"""SQLAlchemy adapter for template assets (2.0)."""

from __future__ import annotations

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
        now = datetime.now(UTC)
        result: list[PackAssetDTO] = []
        async with self._sessionmaker.begin() as session:
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
                # Store raw content as utf-8 with fallback to base64
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
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for m in models:
                    # Content stored as string; recover bytes
                    raw: bytes
                    try:
                        raw = m.content.encode("utf-8")
                        # If content was base64-encoded due to binary, try decode?
                        # Heuristic: if size != len(raw) and sha mismatch, try base64
                        if m.size != len(raw):
                            try:
                                decoded = base64.b64decode(m.content, validate=True)
                                if len(decoded) == m.size:
                                    raw = decoded
                            except Exception as exc:
                                logger.debug(
                                    "template_asset.base64_fallback_failed",
                                    path=m.path,
                                    error=str(exc),
                                )
                    except Exception as exc:
                        logger.warning(
                            "template_asset.content_encode_failed",
                            path=m.path,
                            error=str(exc),
                        )
                        raw = b""
                    info = tarfile.TarInfo(name=m.path)
                    info.size = len(raw)
                    info.mtime = int(m.created_at.timestamp())
                    info.mode = 0o644
                    tar.addfile(info, io.BytesIO(raw))
            buf.seek(0)
            return buf.getvalue()
