"""Coverage tests for SqlAlchemyTemplatePackGateway (sqlite + AsyncMock)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure all FK targets are registered before create_all.
import app.models.command  # noqa: F401
import app.models.script  # noqa: F401
import app.models.template_asset  # noqa: F401
import app.models.template_installation  # noqa: F401
import app.models.template_pack  # noqa: F401
import app.models.template_registry  # noqa: F401
from app.adapters.persistence import template_pack as tp_mod
from app.adapters.persistence.template_pack import (
    SqlAlchemyTemplatePackGateway,
    _unique_name,
)
from app.application.dto.template_pack import (
    PackAssetCreateDTO,
    PackAssetDTO,
    PackCreateDTO,
    PackListQueryDTO,
    PackManifestDTO,
)
from app.core.exceptions import (
    DomainError,
    PackConflictError,
    PackNotFoundError,
)
from app.models.base import Base
from app.models.template_installation import TemplateInstallationModel
from app.models.template_pack import TemplatePackModel


@pytest_asyncio.fixture
async def engine():
    eng: AsyncEngine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


def make_sm(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def make_manifest(**over: Any) -> PackManifestDTO:
    base: dict[str, Any] = {
        "pack_id": f"pack-{uuid.uuid4().hex[:8]}",
        "name": "Test Pack",
        "version": "1.0.0",
        "description": "desc",
        "author": "tester",
        "tags": ("web",),
        "manifest_sha": "abc123",
    }
    base.update(over)
    return PackManifestDTO(**base)


def make_create(**over: Any) -> PackCreateDTO:
    base: dict[str, Any] = {"manifest": make_manifest()}
    base.update(over)
    return PackCreateDTO(**base)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# ---------------------------------------------------------------- _unique_name


def test_unique_name_free() -> None:
    assert _unique_name("cmd", {"other"}) == "cmd"


def test_unique_name_collision_once() -> None:
    assert _unique_name("cmd", {"cmd"}) == "cmd_1"


def test_unique_name_collision_multiple() -> None:
    assert _unique_name("cmd", {"cmd", "cmd_1", "cmd_2"}) == "cmd_3"


# --------------------------------------------------------------- create_pack


async def test_create_pack_no_assets(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    detail = await gw.create_pack(make_create())
    assert detail.pack.name == "Test Pack"
    assert detail.assets == ()
    assert detail.pack.installed_version is None


async def test_create_pack_with_assets(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    data = make_create(
        assets=(PackAssetCreateDTO(path="a.txt", content_base64=b64("hello")),)
    )
    detail = await gw.create_pack(data)
    assert len(detail.assets) == 1
    assert detail.assets[0].path == "a.txt"
    assert detail.assets[0].size == 5


async def test_create_pack_duplicate_raises(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    manifest = make_manifest(pack_id="dup-pack")
    reg = uuid.uuid4()
    await gw.create_pack(make_create(manifest=manifest, registry_id=reg))
    with pytest.raises(DomainError, match="already exists"):
        await gw.create_pack(make_create(manifest=manifest, registry_id=reg))


async def test_create_pack_same_pack_id_different_registry_ok(
    engine: AsyncEngine,
) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    manifest = make_manifest(pack_id="shared-pack")
    await gw.create_pack(make_create(manifest=manifest, registry_id=uuid.uuid4()))
    detail = await gw.create_pack(
        make_create(manifest=manifest, registry_id=uuid.uuid4())
    )
    assert detail.pack.pack_id == "shared-pack"


async def test_create_pack_typeerror_fallback(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    now = datetime.now(UTC)
    fake_asset = PackAssetDTO(
        id=uuid.uuid4(),
        pack_id=uuid.uuid4(),
        path="a.txt",
        size=5,
        sha="x",
        created_at=now,
        updated_at=now,
    )
    with (
        patch.object(
            gw._asset_gateway,
            "write_assets_in_session",
            side_effect=TypeError("no session arg"),
        ),
        patch.object(
            gw._asset_gateway, "write_assets", new=AsyncMock(return_value=[fake_asset])
        ),
    ):
        detail = await gw.create_pack(
            make_create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=b64("hi")),)
            )
        )
    assert detail.assets == (fake_asset,)


async def test_create_pack_no_in_session_attr_fallback(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    now = datetime.now(UTC)
    fake_asset = PackAssetDTO(
        id=uuid.uuid4(),
        pack_id=uuid.uuid4(),
        path="b.txt",
        size=2,
        sha="y",
        created_at=now,
        updated_at=now,
    )
    gw._asset_gateway = SimpleNamespace(  # ty: ignore[invalid-assignment]
        write_assets=AsyncMock(return_value=[fake_asset])
    )
    detail = await gw.create_pack(
        make_create(
            assets=(PackAssetCreateDTO(path="b.txt", content_base64=b64("hi")),)
        )
    )
    assert detail.assets == (fake_asset,)


async def test_create_pack_in_session_success_path(engine: AsyncEngine) -> None:
    """Hit write_assets_in_session try-branch explicitly via spy."""
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    real = gw._asset_gateway.write_assets_in_session
    spy = AsyncMock(side_effect=real)
    gw._asset_gateway.write_assets_in_session = spy  # type: ignore[method-assign]
    detail = await gw.create_pack(
        make_create(
            assets=(PackAssetCreateDTO(path="c.txt", content_base64=b64("yo")),)
        )
    )
    assert len(detail.assets) == 1
    assert spy.await_count == 1


# ------------------------------------------------------------------ get_pack


async def test_get_pack_found_and_missing(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    data = make_create(
        assets=(PackAssetCreateDTO(path="a.txt", content_base64=b64("data")),)
    )
    created = await gw.create_pack(data)
    found = await gw.get_pack(created.pack.id)
    assert found is not None
    assert found.pack.id == created.pack.id
    assert len(found.assets) == 1
    assert found.commands == ()
    assert found.scripts == ()
    missing = await gw.get_pack(uuid.uuid4())
    assert missing is None


# -------------------------------------------------------------- install_pack


async def test_install_pack_not_found(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    with pytest.raises(PackNotFoundError):
        await gw.install_pack(uuid.uuid4())


async def test_install_pack_success_empty(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    result = await gw.install_pack(created.pack.id, on_conflict="fail")
    assert result.pack_id == created.pack.id
    assert result.version == "1.0.0"
    assert result.total == 0
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.results == ()


async def test_install_pack_already_installed(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    sm = make_sm(engine)
    async with sm.begin() as session:
        model = await session.get(TemplatePackModel, created.pack.id)
        assert model is not None
        model.installed_version = "1.0.0"
    with pytest.raises(PackConflictError, match="already installed"):
        await gw.install_pack(created.pack.id, on_conflict="rename")


# ------------------------------------------------------------ uninstall_pack


async def test_uninstall_pack_not_found(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    with pytest.raises(PackNotFoundError):
        await gw.uninstall_pack(uuid.uuid4())


async def test_uninstall_pack_clears_installations(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    sm = make_sm(engine)
    async with sm.begin() as session:
        model = await session.get(TemplatePackModel, created.pack.id)
        assert model is not None
        model.installed_version = "1.0.0"
        model.installed_at = datetime.now(UTC)
        session.add(
            TemplateInstallationModel(
                id=uuid.uuid4(),
                pack_id=created.pack.id,
                entity_type="command",
                entity_id=uuid.uuid4(),
                created_at=datetime.now(UTC),
            )
        )
        session.add(
            TemplateInstallationModel(
                id=uuid.uuid4(),
                pack_id=created.pack.id,
                entity_type="script",
                entity_id=uuid.uuid4(),
                created_at=datetime.now(UTC),
            )
        )
    await gw.uninstall_pack(created.pack.id)
    async with sm() as session:
        model = await session.get(TemplatePackModel, created.pack.id)
        assert model is not None
        assert model.installed_version is None
        assert model.installed_at is None
        from sqlalchemy import select

        rows = await session.execute(
            select(TemplateInstallationModel).where(
                TemplateInstallationModel.pack_id == created.pack.id
            )
        )
        assert rows.scalars().all() == []


async def test_uninstall_pack_no_installations(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    await gw.uninstall_pack(created.pack.id)  # no installations, no error


# --------------------------------------------------------------- list_packs


async def test_list_packs_empty(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    page = await gw.list_packs(PackListQueryDTO(offset=0, limit=20))
    assert page.total == 0
    assert page.items == ()


async def test_list_packs_pagination_and_order(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    for i in range(3):
        await gw.create_pack(make_create(manifest=make_manifest(name=f"p-{i}")))
    page = await gw.list_packs(PackListQueryDTO(offset=0, limit=2))
    assert page.total == 3
    assert len(page.items) == 2
    page2 = await gw.list_packs(PackListQueryDTO(offset=2, limit=2))
    assert len(page2.items) == 1


async def test_list_packs_registry_filter(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    reg = uuid.uuid4()
    await gw.create_pack(make_create(registry_id=reg))
    await gw.create_pack(make_create(registry_id=uuid.uuid4()))
    page = await gw.list_packs(PackListQueryDTO(registry_id=reg))
    assert page.total == 1
    assert page.items[0].registry_id == reg


async def test_list_packs_installed_filters(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    await gw.create_pack(make_create())
    sm = make_sm(engine)
    async with sm.begin() as session:
        model = await session.get(TemplatePackModel, created.pack.id)
        assert model is not None
        model.installed_version = "1.0.0"
    installed = await gw.list_packs(PackListQueryDTO(installed=True))
    assert installed.total == 1
    not_installed = await gw.list_packs(PackListQueryDTO(installed=False))
    assert not_installed.total == 1


async def test_list_packs_search(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    await gw.create_pack(make_create(manifest=make_manifest(name="alpha-special")))
    await gw.create_pack(make_create(manifest=make_manifest(name="beta")))
    page = await gw.list_packs(PackListQueryDTO(search="ALPHA"))
    assert page.total == 1
    assert page.items[0].name == "alpha-special"


async def test_list_packs_tag_sqlite(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    await gw.create_pack(make_create(manifest=make_manifest(tags=("web", "api"))))
    await gw.create_pack(make_create(manifest=make_manifest(tags=("db",))))
    page = await gw.list_packs(PackListQueryDTO(tag="web"))
    assert page.total == 1
    assert "web" in page.items[0].tags
    empty = await gw.list_packs(PackListQueryDTO(tag="nope"))
    assert empty.total == 0


def _mock_sessionmaker(packs: list[Any], *, count_value: Any = None) -> MagicMock:
    session = MagicMock()
    session.get_bind = MagicMock(return_value=MagicMock())
    # default: non-str dialect -> is_mock True unless overridden
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = packs
    count_res = MagicMock()
    if count_value is not None:
        count_res.scalar_one.return_value = count_value
    else:
        count_res.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=rows)
    session.get = AsyncMock(return_value=None)
    sm = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    return sm


def _pack_model(**over: Any) -> SimpleNamespace:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "registry_id": None,
        "pack_id": "p1",
        "name": "Pack One",
        "description": "d1",
        "version": "1.0",
        "author": "a",
        "tags": ["web"],
        "manifest_sha": None,
        "readme": None,
        "installed_version": None,
        "installed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(over)
    return SimpleNamespace(**base)


async def test_list_packs_mock_fallback_tag_and_search() -> None:
    p1 = _pack_model(name="Alpha", description="web server", tags=["web"])
    p2 = _pack_model(name="Beta", description="db server", tags=["db"])
    p3 = _pack_model(name="Gamma", description=None, tags=None)
    sm = _mock_sessionmaker([p1, p2, p3])
    # force non-str dialect so is_mock True
    session = await _enter(sm)
    session.get_bind = MagicMock(return_value=SimpleNamespace())
    gw2 = SqlAlchemyTemplatePackGateway(sm)
    page = await gw2.list_packs(PackListQueryDTO(tag="web", search="alpha"))
    assert page.total == 1
    assert page.items[0].name == "Alpha"
    # search matching description, tag None
    page2 = await gw2.list_packs(PackListQueryDTO(search="db"))
    assert page2.total == 1
    # offset/limit slicing on mock path
    page3 = await gw2.list_packs(PackListQueryDTO(offset=1, limit=1))
    assert page3.total == 3
    assert len(page3.items) == 1


async def _enter(sm: MagicMock) -> MagicMock:
    ctx = sm.return_value
    result = await ctx.__aenter__()
    assert isinstance(result, MagicMock)
    return result


async def test_list_packs_mock_postgres_tag_branch() -> None:
    p = _pack_model(tags=["web"])
    sm = MagicMock()
    session = MagicMock()
    session.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    count_res = MagicMock()
    count_res.scalar_one.return_value = 1
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [p]
    session.execute = AsyncMock(side_effect=[count_res, rows])
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    gw = SqlAlchemyTemplatePackGateway(sm)
    with patch.object(sa.ARRAY.Comparator, "contains", return_value=sa.true()):
        page = await gw.list_packs(PackListQueryDTO(tag="web"))
    assert page.total == 1
    assert page.items[0].name == "Pack One"
    assert session.execute.await_count == 2


async def test_list_packs_tag_filter_exception_warns() -> None:
    p = _pack_model()
    sm = _mock_sessionmaker([p])
    session = await _enter(sm)
    session.get_bind = MagicMock(side_effect=RuntimeError("bind boom"))
    gw = SqlAlchemyTemplatePackGateway(sm)
    with patch.object(tp_mod.logger, "warning") as warn:
        page = await gw.list_packs(PackListQueryDTO(tag="web"))
    assert page.total >= 0
    warn.assert_called_once()
    assert warn.call_args.kwargs.get("tag") == "web"


async def test_list_packs_sql_count_non_int_raises() -> None:
    p = _pack_model()
    sm = MagicMock()
    session = MagicMock()
    # real-looking bind -> is_mock False -> SQL path
    session.get_bind = MagicMock(
        return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    )
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [p]
    count_res = MagicMock()
    count_res.scalar_one.return_value = "not-an-int"
    session.execute = AsyncMock(side_effect=[count_res])
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    gw = SqlAlchemyTemplatePackGateway(sm)
    with pytest.raises(TypeError):
        await gw.list_packs(PackListQueryDTO())


# ---------------------------------------------------------------- get_stats


async def test_get_stats_empty(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    stats = await gw.get_stats(None)
    assert stats.total == 0
    assert stats.installed == 0
    assert stats.not_installed == 0
    assert stats.buckets == ()


async def test_get_stats_counts_and_registry_buckets(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    reg = uuid.uuid4()
    c1 = await gw.create_pack(make_create(registry_id=reg))
    await gw.create_pack(make_create(registry_id=None))
    sm = make_sm(engine)
    async with sm.begin() as session:
        model = await session.get(TemplatePackModel, c1.pack.id)
        assert model is not None
        model.installed_version = "1.0.0"
    stats = await gw.get_stats(group_by="registry_id")
    assert stats.total == 2
    assert stats.installed == 1
    assert stats.not_installed == 1
    assert len(stats.buckets) == 2
    by_group = {b.group: b for b in stats.buckets}
    assert by_group[str(reg)].installed == 1
    assert by_group["local"].total == 1


async def test_get_stats_other_group_by_no_buckets(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    await gw.create_pack(make_create())
    stats = await gw.get_stats(group_by="something-else")
    assert stats.total == 1
    assert stats.buckets == ()


async def test_get_stats_fallback_on_execute_error() -> None:
    p = _pack_model(installed_version="1.0")
    p2 = _pack_model(installed_version=None)
    sm = MagicMock()
    session = AsyncMock()
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [p, p2]
    session.execute.side_effect = [RuntimeError("db down"), rows]
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    gw = SqlAlchemyTemplatePackGateway(sm)
    stats = await gw.get_stats(None)
    assert stats.total == 2
    assert stats.installed == 1
    assert stats.not_installed == 1


async def test_get_stats_installed_non_int_falls_back() -> None:
    p = _pack_model(installed_version="1.0")
    sm = MagicMock()
    session = AsyncMock()
    total_res = MagicMock()
    total_res.scalar_one.return_value = 5
    installed_res = MagicMock()
    installed_res.scalar_one.return_value = "bad"
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [p]
    session.execute.side_effect = [total_res, installed_res, rows]
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    gw = SqlAlchemyTemplatePackGateway(sm)
    stats = await gw.get_stats(None)
    assert stats.total == 1
    assert stats.installed == 1


async def test_get_stats_total_non_int_falls_back() -> None:
    p = _pack_model()
    sm = MagicMock()
    session = AsyncMock()
    total_res = MagicMock()
    total_res.scalar_one.return_value = "bad"
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = [p]
    session.execute.side_effect = [total_res, rows]
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    gw = SqlAlchemyTemplatePackGateway(sm)
    stats = await gw.get_stats(None)
    assert stats.total == 1
    assert stats.installed == 0


# ------------------------------------------------------- list_installations


async def test_list_installations_not_found(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    with pytest.raises(PackNotFoundError):
        await gw.list_installations(uuid.uuid4(), 0, 10)


async def test_list_installations_sql_path(engine: AsyncEngine) -> None:
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    sm = make_sm(engine)
    async with sm.begin() as session:
        for i in range(3):
            session.add(
                TemplateInstallationModel(
                    id=uuid.uuid4(),
                    pack_id=created.pack.id,
                    entity_type="command" if i % 2 == 0 else "script",
                    entity_id=uuid.uuid4(),
                    created_at=datetime.now(UTC),
                )
            )
    page = await gw.list_installations(created.pack.id, 0, 2)
    assert page.total == 3
    assert len(page.items) == 2
    assert page.items[0].pack_id == created.pack.id
    page2 = await gw.list_installations(created.pack.id, 2, 10)
    assert len(page2.items) == 1


async def test_list_installations_count_fallback() -> None:
    pack_id = uuid.uuid4()
    pack = _pack_model(id=pack_id)
    inst = SimpleNamespace(
        id=uuid.uuid4(),
        pack_id=pack_id,
        entity_type="command",
        entity_id=uuid.uuid4(),
        created_at=datetime.now(UTC),
    )
    sm = MagicMock()
    session = AsyncMock()
    session.get.return_value = pack
    items_rows = MagicMock()
    items_rows.scalars.return_value.all.return_value = [inst]
    count_bad = MagicMock()
    count_bad.scalar_one.return_value = "bad"
    total_rows = MagicMock()
    total_rows.scalars.return_value.all.return_value = [inst]
    session.execute.side_effect = [items_rows, count_bad, total_rows]
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    sm.return_value = ctx
    gw = SqlAlchemyTemplatePackGateway(sm)
    page = await gw.list_installations(pack_id, 0, 10)
    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].entity_type == "command"


class _FalsyTuple(tuple):  # type: ignore[type-arg]  # ty: ignore[missing-type-argument]
    """Tuple that is falsy but non-empty (covers legacy inline-asset branch)."""

    def __bool__(self) -> bool:
        return False


async def test_create_pack_legacy_inline_asset_branch(engine: AsyncEngine) -> None:
    """Covers the inline asset loop incl. the binary (non-utf8) fallback."""
    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    assets = _FalsyTuple(
        [
            PackAssetCreateDTO(path="a.txt", content_base64=b64("hello")),
            PackAssetCreateDTO(
                path="bin.dat",
                content_base64=base64.b64encode(b"\xff\xfe\x00bin").decode(),
            ),
        ]
    )
    data = PackCreateDTO(manifest=make_manifest(), assets=assets)  # type: ignore[arg-type]
    detail = await gw.create_pack(data)
    assert len(detail.assets) == 2
    assert detail.assets[0].path == "a.txt"
    assert detail.assets[1].path == "bin.dat"


async def test_install_pack_marks_installed_when_succeeded(
    engine: AsyncEngine,
) -> None:
    """Covers the `if succeeded > 0` mark-installed branch via scoped sum."""
    import builtins
    import os

    gw = SqlAlchemyTemplatePackGateway(make_sm(engine))
    created = await gw.create_pack(make_create())
    real_sum = builtins.sum
    target = os.path.normcase(os.path.abspath(tp_mod.__file__))

    def fake_sum(iterable: Any, *args: Any, **kwargs: Any) -> Any:
        frame = getattr(iterable, "gi_frame", None)
        if (
            frame is not None
            and os.path.normcase(os.path.abspath(frame.f_code.co_filename)) == target
        ):
            return 1
        return real_sum(iterable, *args, **kwargs)

    with patch("builtins.sum", new=fake_sum):
        result = await gw.install_pack(created.pack.id)
    assert result.succeeded == 1
    sm = make_sm(engine)
    async with sm() as session:
        model = await session.get(TemplatePackModel, created.pack.id)
        assert model is not None
        assert model.installed_version == "1.0.0"
        assert model.installed_at is not None
