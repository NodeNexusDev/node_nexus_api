"""SQLite-backed template service factories for unit tests (no live infra)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
from app.adapters.persistence.template_registry import (
    SqlAlchemyTemplateRegistryGateway,
)
from app.application.ports.template_source import FetchedPack
from app.application.services.template_pack_service import TemplatePackService
from app.application.services.template_registry_service import TemplateRegistryService
from app.models.api_key import APIKeyModel  # noqa: F401
from app.models.audit_log import AuditLogModel  # noqa: F401
from app.models.audit_outbox import AuditOutboxModel  # noqa: F401
from app.models.base import Base
from app.models.command import CommandModel  # noqa: F401
from app.models.command_execution import CommandExecutionModel  # noqa: F401
from app.models.compose_project import ComposeProjectModel  # noqa: F401
from app.models.favorite import FavoriteModel  # noqa: F401
from app.models.node import NodeModel  # noqa: F401
from app.models.node_status_history import NodeStatusHistoryModel  # noqa: F401
from app.models.refresh_token import RefreshTokenModel  # noqa: F401
from app.models.script import ScriptModel  # noqa: F401
from app.models.script_execution import ScriptExecutionModel  # noqa: F401
from app.models.script_schedule import ScriptScheduleModel  # noqa: F401
from app.models.template_asset import TemplateAssetModel  # noqa: F401
from app.models.template_installation import TemplateInstallationModel  # noqa: F401
from app.models.template_pack import TemplatePackModel  # noqa: F401
from app.models.template_registry import TemplateRegistryModel  # noqa: F401
from app.models.user import UserModel  # noqa: F401


class FakeCipher:
    """Identity credential cipher for unit tests."""

    def encrypt(self, plaintext: str) -> str:
        return f"enc:{plaintext}"

    def decrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return value.removeprefix("enc:")


class FakeSource:
    """Canned GitHub source for sync tests (no network)."""

    def __init__(self, packs: list[FetchedPack] | None = None) -> None:
        self._packs = list(packs or [])
        self.seen: tuple[str, str, str, str | None] | None = None

    async def fetch_packs(
        self, owner: str, repo: str, branch: str, token: str | None
    ) -> list[FetchedPack]:
        self.seen = (owner, repo, branch, token)
        return list(self._packs)


async def make_sessionmaker() -> tuple[async_sessionmaker[AsyncSession], AsyncEngine]:
    """Create a fresh in-memory SQLite sessionmaker with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return sessionmaker, engine


async def make_pack_service() -> tuple[TemplatePackService, AsyncEngine]:
    """Build a DB-backed pack service with isolated storage."""
    sessionmaker, engine = await make_sessionmaker()
    return TemplatePackService(SqlAlchemyTemplatePackGateway(sessionmaker)), engine


async def make_registry_service(
    source: FakeSource | None = None,
) -> tuple[TemplateRegistryService, FakeSource, AsyncEngine]:
    """Build a DB-backed registry service with isolated storage."""
    sessionmaker, engine = await make_sessionmaker()
    pack_gateway = SqlAlchemyTemplatePackGateway(sessionmaker)
    gateway = SqlAlchemyTemplateRegistryGateway(sessionmaker, FakeCipher())
    fake = source or FakeSource()
    return TemplateRegistryService(gateway, pack_gateway, fake), fake, engine
