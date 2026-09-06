"""Boost coverage to >95% for low-coverage modules."""

# ruff: noqa: E501
from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
    JobSubmissionEvent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_maker(session: MagicMock | AsyncMock) -> MagicMock:
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=session)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=session)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    maker = MagicMock()
    maker.return_value = mock_ctx
    maker.begin.return_value = mock_begin
    return maker


def _make_pack_model(**overrides):
    now = datetime.now(UTC)
    defaults = {
        "id": uuid.uuid4(),
        "registry_id": None,
        "pack_id": "test-pack",
        "name": "TestPack",
        "description": "desc",
        "version": "1.0.0",
        "author": "author",
        "tags": ["t1", "t2"],
        "manifest_sha": "sha",
        "readme": "readme",
        "installed_version": None,
        "installed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# template_pack _unique_name
# ---------------------------------------------------------------------------


class TestUniqueName:
    def test_base_not_in_existing(self):
        from app.adapters.persistence.template_pack import _unique_name

        assert _unique_name("foo", set()) == "foo"
        assert _unique_name("foo", {"bar"}) == "foo"

    def test_single_collision(self):
        from app.adapters.persistence.template_pack import _unique_name

        assert _unique_name("foo", {"foo"}) == "foo_1"

    def test_multiple_collisions(self):
        from app.adapters.persistence.template_pack import _unique_name

        assert _unique_name("foo", {"foo", "foo_1"}) == "foo_2"
        assert _unique_name("foo", {"foo", "foo_1", "foo_2", "foo_3"}) == "foo_4"


# ---------------------------------------------------------------------------
# template_pack SqlAlchemyTemplatePackGateway
# ---------------------------------------------------------------------------


class TestTemplatePackGatewayCreate:
    @pytest.mark.asyncio
    async def test_create_pack_duplicate(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import PackCreateDTO, PackManifestDTO
        from app.core.exceptions import DomainError

        session = AsyncMock()
        # duplicate check -> returns existing
        mock_exists = MagicMock()
        mock_exists.scalar_one_or_none.return_value = MagicMock()
        session.execute = AsyncMock(return_value=mock_exists)
        session.flush = AsyncMock()
        session.add = MagicMock()
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        # patch asset gateway to avoid extra calls
        gw._asset_gateway = MagicMock()
        gw._asset_gateway.write_assets_in_session = AsyncMock(return_value=[])
        data = PackCreateDTO(
            manifest=PackManifestDTO(pack_id="dup", name="n", version="1.0.0"),
            registry_id=uuid.uuid4(),
        )
        with pytest.raises(DomainError, match="already exists"):
            await gw.create_pack(data)

    @pytest.mark.asyncio
    async def test_create_pack_no_assets(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import PackCreateDTO, PackManifestDTO

        session = AsyncMock()
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_none)
        session.flush = AsyncMock()
        session.add = MagicMock()
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        gw._asset_gateway = MagicMock()
        gw._asset_gateway.write_assets_in_session = AsyncMock(return_value=[])
        data = PackCreateDTO(
            manifest=PackManifestDTO(
                pack_id="pack-no-assets", name="n", version="1.0.0"
            ),
        )
        res = await gw.create_pack(data)
        assert res.pack.pack_id == "pack-no-assets"
        assert res.assets == ()

    @pytest.mark.asyncio
    async def test_create_pack_with_assets_write_in_session(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import (
            PackAssetCreateDTO,
            PackAssetDTO,
            PackCreateDTO,
            PackManifestDTO,
        )

        session = AsyncMock()
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_none)
        session.flush = AsyncMock()
        session.add = MagicMock()
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        asset_dto = PackAssetDTO(
            id=uuid.uuid4(),
            pack_id=uuid.uuid4(),
            path="a.txt",
            size=5,
            sha="sha",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        gw._asset_gateway = MagicMock()
        gw._asset_gateway.write_assets_in_session = AsyncMock(return_value=(asset_dto,))
        b64 = base64.b64encode(b"hello").decode()
        data = PackCreateDTO(
            manifest=PackManifestDTO(pack_id="with-assets", name="n", version="1.0.0"),
            assets=(PackAssetCreateDTO(path="a.txt", content_base64=b64),),
        )
        res = await gw.create_pack(data)
        assert len(res.assets) == 1
        gw._asset_gateway.write_assets_in_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_pack_write_in_session_typeerror_fallback(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import (
            PackAssetCreateDTO,
            PackAssetDTO,
            PackCreateDTO,
            PackManifestDTO,
        )

        session = AsyncMock()
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_none)
        session.flush = AsyncMock()
        session.add = MagicMock()
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        asset_dto = PackAssetDTO(
            id=uuid.uuid4(),
            pack_id=uuid.uuid4(),
            path="a.txt",
            size=5,
            sha="sha",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        gw._asset_gateway = MagicMock()
        gw._asset_gateway.write_assets_in_session = AsyncMock(
            side_effect=TypeError("bad")
        )
        gw._asset_gateway.write_assets = AsyncMock(return_value=(asset_dto,))
        b64 = base64.b64encode(b"hello").decode()
        data = PackCreateDTO(
            manifest=PackManifestDTO(
                pack_id="fallback-typeerror", name="n", version="1.0.0"
            ),
            assets=(PackAssetCreateDTO(path="a.txt", content_base64=b64),),
        )
        res = await gw.create_pack(data)
        assert len(res.assets) == 1
        gw._asset_gateway.write_assets.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_pack_without_write_in_session_attr(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import (
            PackAssetCreateDTO,
            PackAssetDTO,
            PackCreateDTO,
            PackManifestDTO,
        )

        session = AsyncMock()
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_none)
        session.flush = AsyncMock()
        session.add = MagicMock()
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)

        # gateway without write_assets_in_session
        class NoInSession:
            async def write_assets(self, pack_id, assets):
                return (
                    PackAssetDTO(
                        id=uuid.uuid4(),
                        pack_id=pack_id,
                        path="a.txt",
                        size=5,
                        sha="sha",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                )

        gw._asset_gateway = NoInSession()  # type: ignore[attr-defined]
        b64 = base64.b64encode(b"hello").decode()
        data = PackCreateDTO(
            manifest=PackManifestDTO(
                pack_id="no-in-session", name="n", version="1.0.0"
            ),
            assets=(PackAssetCreateDTO(path="a.txt", content_base64=b64),),
        )
        res = await gw.create_pack(data)
        assert len(res.assets) == 1

    @pytest.mark.asyncio
    async def test_create_pack_else_branch_dead_code_via_falsy_list(self):
        """Cover the else branch for asset handling (lines 117-135) via falsy iterable."""
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import (
            PackAssetCreateDTO,
            PackCreateDTO,
            PackManifestDTO,
        )

        session = AsyncMock()
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_none)
        session.flush = AsyncMock()
        session.add = MagicMock()
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        gw._asset_gateway = MagicMock()

        # Create a falsy list that still contains an item -> triggers else branch with iteration
        class FalsyList(list):
            def __bool__(self):
                return False

        # Use valid base64 for utf-8 content
        b64 = base64.b64encode(b"hello world").decode()
        asset = PackAssetCreateDTO(path="file.txt", content_base64=b64)
        falsy_assets = FalsyList([asset])

        # Also test non-utf8 path to cover base64 fallback
        raw_bytes = bytes([0xFF, 0xFE, 0xFD])
        b64_bin = base64.b64encode(raw_bytes).decode()
        asset_bin = PackAssetCreateDTO(path="bin.dat", content_base64=b64_bin)
        falsy_assets_bin = FalsyList([asset_bin])

        for flist, pack_id in [
            (falsy_assets, "falsy-utf8"),
            (falsy_assets_bin, "falsy-bin"),
        ]:
            data = PackCreateDTO(
                manifest=PackManifestDTO(pack_id=pack_id, name="n", version="1.0.0"),
                assets=flist,  # type: ignore[arg-type]
            )
            res = await gw.create_pack(data)
            # In dead code path, assets should be created via direct loop
            assert len(res.assets) == 1
            assert res.assets[0].path in ("file.txt", "bin.dat")

    @pytest.mark.asyncio
    async def test_get_pack_found_and_not_found(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        # not found
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        gw._asset_gateway = MagicMock()
        gw._asset_gateway.list_assets = AsyncMock(return_value=())
        res = await gw.get_pack(uuid.uuid4())
        assert res is None

        # found
        session2 = AsyncMock()
        model = _make_pack_model()
        session2.get = AsyncMock(return_value=model)
        maker2 = _make_maker(session2)
        gw2 = SqlAlchemyTemplatePackGateway(maker2)
        gw2._asset_gateway = MagicMock()
        gw2._asset_gateway.list_assets = AsyncMock(return_value=())
        res2 = await gw2.get_pack(model.id)
        assert res2 is not None
        assert res2.pack.id == model.id


class TestTemplatePackGatewayInstall:
    @pytest.mark.asyncio
    async def test_install_not_found(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.core.exceptions import PackNotFoundError

        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        with pytest.raises(PackNotFoundError):
            await gw.install_pack(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_install_already_installed(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.core.exceptions import PackConflictError

        session = AsyncMock()
        model = _make_pack_model(installed_version="1.0.0")
        session.get = AsyncMock(return_value=model)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        with pytest.raises(PackConflictError):
            await gw.install_pack(model.id)

    @pytest.mark.asyncio
    async def test_install_success_empty(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        session = AsyncMock()
        model = _make_pack_model(installed_version=None, version="1.0.0")
        session.get = AsyncMock(return_value=model)
        # mock command/script name fetches
        mock_cmd = MagicMock()
        mock_cmd.all.return_value = []
        mock_scr = MagicMock()
        mock_scr.all.return_value = []
        # session.execute called twice for cmd and script names
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(all=MagicMock(return_value=[])),
                MagicMock(all=MagicMock(return_value=[])),
            ]
        )

        # Actually need to mock correctly: session.execute returns object with .all()
        # Let's patch simpler: make execute return MagicMock with .all returning []
        async def fake_execute(q):
            m = MagicMock()
            m.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=fake_execute)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        res = await gw.install_pack(model.id, on_conflict="rename")
        assert res.pack_id == model.id
        assert res.version == "1.0.0"
        assert res.total == 0

    @pytest.mark.asyncio
    async def test_uninstall_not_found_and_success(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.core.exceptions import PackNotFoundError

        # not found
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        with pytest.raises(PackNotFoundError):
            await gw.uninstall_pack(uuid.uuid4())

        # success with installations
        session2 = AsyncMock()
        model = _make_pack_model(
            installed_version="1.0.0", installed_at=datetime.now(UTC)
        )
        session2.get = AsyncMock(return_value=model)
        mock_inst = MagicMock()
        mock_inst.id = uuid.uuid4()
        mock_rows = MagicMock()
        mock_rows.scalars.return_value.all.return_value = [mock_inst]
        session2.execute = AsyncMock(return_value=mock_rows)
        session2.delete = AsyncMock()
        maker2 = _make_maker(session2)
        gw2 = SqlAlchemyTemplatePackGateway(maker2)
        await gw2.uninstall_pack(model.id)
        assert model.installed_version is None


class TestTemplatePackGatewayListPacks:
    @pytest.mark.asyncio
    async def test_list_packs_is_mock_true_with_filters(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import PackListQueryDTO

        # is_mock True: session.get_bind raises or returns non-string dialect
        session = AsyncMock()
        session.get_bind = MagicMock(side_effect=Exception("no bind"))
        # Prepare pack models
        now = datetime.now(UTC)
        m1 = _make_pack_model(
            name="SearchMe",
            description="desc search",
            tags=["t1"],
            registry_id=uuid.uuid4(),
            installed_version=None,
            created_at=now,
        )
        m2 = _make_pack_model(
            name="Other",
            description="other",
            tags=["t2"],
            registry_id=uuid.uuid4(),
            installed_version="1.0.0",
            created_at=now - timedelta(days=1),
        )
        m3 = _make_pack_model(
            name="TagPack",
            description="tag",
            tags=["t1"],
            registry_id=m1.registry_id,
            installed_version=None,
            created_at=now - timedelta(hours=1),
        )

        mock_rows = MagicMock()
        mock_rows.scalars.return_value.all.return_value = [m1, m2, m3]
        session.execute = AsyncMock(return_value=mock_rows)

        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)

        # For is_mock True, registry_id and installed are NOT filtered in python fallback,
        # only tag and search are python-filtered. So we test those for is_mock True
        # and test registry/installed via is_mock False path below.
        # So here we just verify that list_packs returns without error and pagination works
        q = PackListQueryDTO(offset=0, limit=10, registry_id=m1.registry_id)
        res = await gw.list_packs(q)
        # In mock mode registry filter is SQL-only, so mock returns all 3 -> total 3 sliced
        assert res.total == 3

        q2 = PackListQueryDTO(offset=0, limit=10, installed=True)
        res2 = await gw.list_packs(q2)
        assert res2.total == 3

        q3 = PackListQueryDTO(offset=0, limit=10, installed=False)
        res3 = await gw.list_packs(q3)
        assert res3.total == 3

        # search filter (case insensitive, checks name and description) -> python filtered
        q4 = PackListQueryDTO(offset=0, limit=10, search="searchme")
        res4 = await gw.list_packs(q4)
        assert any("SearchMe" in p.name for p in res4.items)

        # search in description
        q5 = PackListQueryDTO(offset=0, limit=10, search="other")
        res5 = await gw.list_packs(q5)
        assert any("Other" in p.name for p in res5.items)

        # tag filter is_mock True uses python fallback
        q6 = PackListQueryDTO(offset=0, limit=10, tag="t1")
        res6 = await gw.list_packs(q6)
        assert all("t1" in p.tags for p in res6.items)

        # pagination offset/limit
        q7 = PackListQueryDTO(offset=1, limit=1)
        res7 = await gw.list_packs(q7)
        assert len(res7.items) == 1

    @pytest.mark.asyncio
    async def test_list_packs_is_mock_false_postgres_and_sqlite(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import PackListQueryDTO

        # is_mock False with postgres dialect
        for dialect_name in ("postgresql", "sqlite"):
            session = AsyncMock()
            bind = MagicMock()
            bind.dialect.name = dialect_name
            session.get_bind = MagicMock(return_value=bind)
            now = datetime.now(UTC)
            m = _make_pack_model(created_at=now)
            # count query returns int
            mock_count = MagicMock()
            mock_count.scalar_one.return_value = 1
            # data query returns one item
            mock_data = MagicMock()
            mock_data.scalars.return_value.all.return_value = [m]
            # need two execute calls: count then data
            # Actually is_mock False path does count first then ordered pagination
            # So execute side_effect should handle both queries
            session.execute = AsyncMock(side_effect=[mock_count, mock_data])

            maker = _make_maker(session)
            gw = SqlAlchemyTemplatePackGateway(maker)

            # tag filter postgres vs sqlite branch
            q = PackListQueryDTO(
                offset=0,
                limit=10,
                tag="t1",
                search="Test",
                installed=True,
                registry_id=uuid.uuid4(),
            )
            # For postgres, tag contains uses postgresql specific, for sqlite uses instr
            # Both should go through without error
            res = await gw.list_packs(q)
            # Verify count path was used
            assert res.total == 1
            assert len(res.items) == 1

        # tag filter exception path - make get_bind for tag section raise internally?
        # The tag filter try/except catches exception and logs warning
        session2 = AsyncMock()
        # First get_bind for is_mock detection succeeds with string
        bind_ok = MagicMock()
        bind_ok.dialect.name = "postgresql"
        # Second get_bind inside tag filter will be called again; we can make it raise via side_effect
        # But code calls session.get_bind() twice, second time inside tag handling
        # We can make second call raise by using side_effect list
        call_count = {"n": 0}

        def get_bind_side():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return bind_ok
            raise RuntimeError("tag bind fail")

        session2.get_bind = MagicMock(side_effect=get_bind_side)
        mock_count2 = MagicMock()
        mock_count2.scalar_one.return_value = 0
        mock_data2 = MagicMock()
        mock_data2.scalars.return_value.all.return_value = []
        session2.execute = AsyncMock(side_effect=[mock_count2, mock_data2])
        maker2 = _make_maker(session2)
        gw2 = SqlAlchemyTemplatePackGateway(maker2)
        q2 = PackListQueryDTO(offset=0, limit=10, tag="t1")
        res2 = await gw2.list_packs(q2)
        # Should still succeed, tag filter warning logged but not raised
        assert res2.total == 0

        # count scalar_one returns non-int -> TypeError
        session3 = AsyncMock()
        bind3 = MagicMock()
        bind3.dialect.name = "postgresql"
        session3.get_bind = MagicMock(return_value=bind3)
        mock_bad = MagicMock()
        mock_bad.scalar_one.return_value = "not int"
        session3.execute = AsyncMock(return_value=mock_bad)
        maker3 = _make_maker(session3)
        gw3 = SqlAlchemyTemplatePackGateway(maker3)
        q3 = PackListQueryDTO(offset=0, limit=10)
        with pytest.raises(TypeError):
            await gw3.list_packs(q3)

    @pytest.mark.asyncio
    async def test_list_packs_non_string_dialect_is_mock(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.application.dto.template_pack import PackListQueryDTO

        session = AsyncMock()
        bind = MagicMock()
        bind.dialect.name = MagicMock()  # not string -> is_mock True
        session.get_bind = MagicMock(return_value=bind)
        m = _make_pack_model()
        mock_rows = MagicMock()
        mock_rows.scalars.return_value.all.return_value = [m]
        session.execute = AsyncMock(return_value=mock_rows)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        res = await gw.list_packs(PackListQueryDTO(offset=0, limit=10))
        assert res.total == 1


class TestTemplatePackGatewayStats:
    @pytest.mark.asyncio
    async def test_get_stats_success_and_group_by(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        session = AsyncMock()
        # Mock successful SQL counts returning ints
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 3
        mock_installed = MagicMock()
        mock_installed.scalar_one.return_value = 1
        m1 = _make_pack_model(registry_id=uuid.uuid4(), installed_version="1.0.0")
        m2 = _make_pack_model(registry_id=m1.registry_id, installed_version=None)
        m3 = _make_pack_model(registry_id=None, installed_version=None)
        mock_packs = MagicMock()
        mock_packs.scalars.return_value.all.return_value = [m1, m2, m3]
        session.execute = AsyncMock(
            side_effect=[mock_total, mock_installed, mock_packs]
        )
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        stats = await gw.get_stats(group_by="registry_id")
        assert stats.total == 3
        assert stats.installed == 1
        assert len(stats.buckets) >= 1

        # also test without group_by
        session2 = AsyncMock()
        mock_total2 = MagicMock()
        mock_total2.scalar_one.return_value = 2
        mock_installed2 = MagicMock()
        mock_installed2.scalar_one.return_value = 0
        mock_packs2 = MagicMock()
        mock_packs2.scalars.return_value.all.return_value = [
            _make_pack_model(),
            _make_pack_model(),
        ]
        session2.execute = AsyncMock(
            side_effect=[mock_total2, mock_installed2, mock_packs2]
        )
        maker2 = _make_maker(session2)
        gw2 = SqlAlchemyTemplatePackGateway(maker2)
        stats2 = await gw2.get_stats(group_by=None)
        assert stats2.buckets == ()

    @pytest.mark.asyncio
    async def test_get_stats_fallback_and_typeerror(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        # Fallback when scalar_one raises
        session = AsyncMock()
        # first execute raises -> goes to except
        m1 = _make_pack_model(installed_version="1.0.0")
        m2 = _make_pack_model(installed_version=None)
        mock_fallback = MagicMock()
        mock_fallback.scalars.return_value.all.return_value = [m1, m2]
        # Need to simulate: first try block fails, so first execute raises, then except does one execute
        # But code in try does 3 executes (total, installed, packs). If any raises, it goes to except which does 1 execute
        # So we can make first execute raise Exception
        session.execute = AsyncMock(side_effect=[Exception("db fail"), mock_fallback])
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        stats = await gw.get_stats(group_by="registry_id")
        assert stats.total == 2
        assert stats.installed == 1

        # TypeError branch: scalar_one returns non-int
        session2 = AsyncMock()
        mock_bad = MagicMock()
        mock_bad.scalar_one.return_value = "not-int"
        mock_fallback2 = MagicMock()
        mock_fallback2.scalars.return_value.all.return_value = [m1]
        session2.execute = AsyncMock(side_effect=[mock_bad, mock_fallback2])
        maker2 = _make_maker(session2)
        gw2 = SqlAlchemyTemplatePackGateway(maker2)
        stats2 = await gw2.get_stats(group_by=None)
        assert stats2.total == 1

        # installed non-int
        session3 = AsyncMock()
        mock_total_ok = MagicMock()
        mock_total_ok.scalar_one.return_value = 5
        mock_inst_bad = MagicMock()
        mock_inst_bad.scalar_one.return_value = None  # not int
        mock_fallback3 = MagicMock()
        mock_fallback3.scalars.return_value.all.return_value = [m1, m2]
        session3.execute = AsyncMock(
            side_effect=[mock_total_ok, mock_inst_bad, mock_fallback3]
        )
        maker3 = _make_maker(session3)
        gw3 = SqlAlchemyTemplatePackGateway(maker3)
        stats3 = await gw3.get_stats(group_by="registry_id")
        assert stats3.total == 2


class TestTemplatePackGatewayListInstallations:
    @pytest.mark.asyncio
    async def test_list_installations_not_found(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.core.exceptions import PackNotFoundError

        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        with pytest.raises(PackNotFoundError):
            await gw.list_installations(uuid.uuid4(), 0, 10)

    @pytest.mark.asyncio
    async def test_list_installations_success_and_fallback_count(self):
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        pack_id = uuid.uuid4()
        session = AsyncMock()
        session.get = AsyncMock(return_value=_make_pack_model(id=pack_id))
        # First execute for paginated items
        inst_model = MagicMock()
        inst_model.id = uuid.uuid4()
        inst_model.pack_id = pack_id
        inst_model.entity_type = "command"
        inst_model.entity_id = uuid.uuid4()
        inst_model.created_at = datetime.now(UTC)
        mock_items = MagicMock()
        mock_items.scalars.return_value.all.return_value = [inst_model]
        # Second execute for count scalar_one -> success
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[mock_items, mock_count])
        maker = _make_maker(session)
        gw = SqlAlchemyTemplatePackGateway(maker)
        res = await gw.list_installations(pack_id, 0, 10)
        assert res.total == 1
        assert len(res.items) == 1

        # Fallback count when scalar_one non-int
        session2 = AsyncMock()
        session2.get = AsyncMock(return_value=_make_pack_model(id=pack_id))
        mock_items2 = MagicMock()
        mock_items2.scalars.return_value.all.return_value = [inst_model]
        mock_bad = MagicMock()
        mock_bad.scalar_one.return_value = "bad"
        mock_fallback = MagicMock()
        mock_fallback.scalars.return_value.all.return_value = [inst_model]
        session2.execute = AsyncMock(side_effect=[mock_items2, mock_bad, mock_fallback])
        maker2 = _make_maker(session2)
        gw2 = SqlAlchemyTemplatePackGateway(maker2)
        res2 = await gw2.list_installations(pack_id, 0, 10)
        assert res2.total == 1

        # Fallback count when exception
        session3 = AsyncMock()
        session3.get = AsyncMock(return_value=_make_pack_model(id=pack_id))
        session3.execute = AsyncMock(
            side_effect=[mock_items, Exception("fail"), mock_fallback]
        )
        maker3 = _make_maker(session3)
        gw3 = SqlAlchemyTemplatePackGateway(maker3)
        res3 = await gw3.list_installations(pack_id, 0, 10)
        assert res3.total == 1


# ---------------------------------------------------------------------------
# user_service
# ---------------------------------------------------------------------------


class TestUserServiceBoost:
    @pytest.mark.asyncio
    async def test_create_user_success(self):
        from app.application.dto.user import UserCreateDTO
        from app.application.services.user_service import UserService

        reader = AsyncMock()
        writer = AsyncMock()
        reader.get_by_email.return_value = None
        view = MagicMock()
        view.id = uuid.uuid4()
        writer.create_user.return_value = view
        svc = UserService(reader, writer)
        res = await svc.create_user(
            "a@b.com", "pass", is_superuser=True, caller_is_superuser=True
        )
        assert res == view
        writer.create_user.assert_awaited_once()
        assert isinstance(writer.create_user.call_args[0][0], UserCreateDTO)

    @pytest.mark.asyncio
    async def test_create_user_not_superuser(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import InsufficientPermissionsError

        svc = UserService(AsyncMock(), AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.create_user("a@b.com", "p", caller_is_superuser=False)

    @pytest.mark.asyncio
    async def test_create_user_duplicate(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import UserAlreadyExistsError

        reader = AsyncMock()
        reader.get_by_email.return_value = MagicMock()
        svc = UserService(reader, AsyncMock())
        with pytest.raises(UserAlreadyExistsError):
            await svc.create_user("a@b.com", "p", caller_is_superuser=True)

    @pytest.mark.asyncio
    async def test_list_users_not_superuser(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import InsufficientPermissionsError

        svc = UserService(AsyncMock(), AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.list_users(0, 10, caller_is_superuser=False)

    @pytest.mark.asyncio
    async def test_list_users_success(self):
        from app.application.services.user_service import UserService

        reader = AsyncMock()
        reader.list_users.return_value = [MagicMock(), MagicMock()]
        reader.count_users.return_value = 5
        svc = UserService(reader, AsyncMock())
        page = await svc.list_users(0, 10, caller_is_superuser=True)
        assert page.total == 5
        assert len(page.items) == 2

    @pytest.mark.asyncio
    async def test_get_user_not_superuser(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import InsufficientPermissionsError

        svc = UserService(AsyncMock(), AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.get_user(uuid.uuid4(), caller_is_superuser=False)

    @pytest.mark.asyncio
    async def test_get_user_not_found(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import UserNotFoundError

        reader = AsyncMock()
        reader.get_user.return_value = None
        svc = UserService(reader, AsyncMock())
        with pytest.raises(UserNotFoundError):
            await svc.get_user(uuid.uuid4(), caller_is_superuser=True)

    @pytest.mark.asyncio
    async def test_get_user_success(self):
        from app.application.services.user_service import UserService

        view = MagicMock()
        reader = AsyncMock()
        reader.get_user.return_value = view
        svc = UserService(reader, AsyncMock())
        res = await svc.get_user(uuid.uuid4(), caller_is_superuser=True)
        assert res == view

    @pytest.mark.asyncio
    async def test_patch_user_not_superuser(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService
        from app.core.exceptions import InsufficientPermissionsError

        svc = UserService(AsyncMock(), AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.patch_user(
                uuid.uuid4(), UserUpdateDTO(email="a@b.com"), caller_is_superuser=False
            )

    @pytest.mark.asyncio
    async def test_patch_user_email_conflict(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService
        from app.core.exceptions import UserAlreadyExistsError

        reader = AsyncMock()
        existing = MagicMock()
        existing.id = uuid.uuid4()
        reader.get_by_email.return_value = existing
        svc = UserService(reader, AsyncMock())
        other_id = uuid.uuid4()
        # ensure different id triggers conflict
        assert existing.id != other_id
        with pytest.raises(UserAlreadyExistsError):
            await svc.patch_user(
                other_id, UserUpdateDTO(email="a@b.com"), caller_is_superuser=True
            )

    @pytest.mark.asyncio
    async def test_patch_user_email_same_id_no_conflict(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService

        uid = uuid.uuid4()
        reader = AsyncMock()
        existing = MagicMock()
        existing.id = uid
        reader.get_by_email.return_value = existing
        writer = AsyncMock()
        writer.update_user.return_value = MagicMock()
        svc = UserService(reader, writer)
        res = await svc.patch_user(
            uid, UserUpdateDTO(email="a@b.com"), caller_is_superuser=True
        )
        assert res is not None

    @pytest.mark.asyncio
    async def test_patch_user_email_not_existing(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService

        reader = AsyncMock()
        reader.get_by_email.return_value = None
        writer = AsyncMock()
        writer.update_user.return_value = MagicMock()
        svc = UserService(reader, writer)
        res = await svc.patch_user(
            uuid.uuid4(), UserUpdateDTO(email="new@b.com"), caller_is_superuser=True
        )
        assert res is not None

    @pytest.mark.asyncio
    async def test_patch_user_no_email_field(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService

        reader = AsyncMock()
        writer = AsyncMock()
        writer.update_user.return_value = MagicMock()
        svc = UserService(reader, writer)
        res = await svc.patch_user(
            uuid.uuid4(), UserUpdateDTO(is_active=True), caller_is_superuser=True
        )
        assert res is not None
        reader.get_by_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_patch_user_not_found(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService
        from app.core.exceptions import UserNotFoundError

        reader = AsyncMock()
        reader.get_by_email.return_value = None
        writer = AsyncMock()
        writer.update_user.return_value = None
        svc = UserService(reader, writer)
        with pytest.raises(UserNotFoundError):
            await svc.patch_user(
                uuid.uuid4(), UserUpdateDTO(email="x@x.com"), caller_is_superuser=True
            )

    @pytest.mark.asyncio
    async def test_patch_user_success(self):
        from app.application.dto.user import UserUpdateDTO
        from app.application.services.user_service import UserService

        reader = AsyncMock()
        reader.get_by_email.return_value = None
        writer = AsyncMock()
        expected = MagicMock()
        writer.update_user.return_value = expected
        svc = UserService(reader, writer)
        res = await svc.patch_user(
            uuid.uuid4(), UserUpdateDTO(is_superuser=True), caller_is_superuser=True
        )
        assert res == expected

    @pytest.mark.asyncio
    async def test_delete_user_not_superuser(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import InsufficientPermissionsError

        svc = UserService(AsyncMock(), AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.delete_user(uuid.uuid4(), caller_is_superuser=False)

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self):
        from app.application.services.user_service import UserService
        from app.core.exceptions import UserNotFoundError

        reader = AsyncMock()
        reader.get_user.return_value = None
        svc = UserService(reader, AsyncMock())
        with pytest.raises(UserNotFoundError):
            await svc.delete_user(uuid.uuid4(), caller_is_superuser=True)


# ---------------------------------------------------------------------------
# persistence user gateway
# ---------------------------------------------------------------------------


class TestSqlAlchemyUserGatewayBoost:
    def _maker(self, session):
        return _make_maker(session)

    @pytest.mark.asyncio
    async def test_update_user_payload_branches(self):
        from app.adapters.persistence.user import SqlAlchemyUserGateway
        from app.application.dto.user import UserUpdateDTO
        from app.models.user import UserModel

        # payload with email and password and is_active and is_superuser
        session = AsyncMock()
        existing = UserModel(
            id=uuid.uuid4(),
            email="old@b.com",
            hashed_password="h",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        updated = UserModel(
            id=existing.id,
            email="new@b.com",
            hashed_password="newhash",
            is_active=False,
            is_superuser=True,
            created_at=datetime.now(UTC),
        )
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=existing)
            repo.update = AsyncMock(return_value=updated)
            hasher = MagicMock()
            hasher.hash.return_value = "newhash"
            maker = self._maker(session)
            gw = SqlAlchemyUserGateway(maker, hasher)
            res = await gw.update_user(
                existing.id,
                UserUpdateDTO(
                    email="new@b.com",
                    password="newpass",
                    is_active=False,
                    is_superuser=True,
                ),
            )
            assert res is not None
            assert res.email == "new@b.com"
            repo.update.assert_awaited_once()
            # check payload contains hashed_password
            assert repo.update.call_args[0][1]["hashed_password"] == "newhash"

    @pytest.mark.asyncio
    async def test_update_user_empty_payload_returns_view(self):
        from app.adapters.persistence.user import SqlAlchemyUserGateway
        from app.application.dto.user import UserUpdateDTO
        from app.models.user import UserModel

        session = AsyncMock()
        model = UserModel(
            id=uuid.uuid4(),
            email="a@b.com",
            hashed_password="h",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=model)
            repo.update = AsyncMock(return_value=model)
            maker = self._maker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            res = await gw.update_user(model.id, UserUpdateDTO())
            assert res is not None
            repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_user_not_found(self):
        from app.adapters.persistence.user import SqlAlchemyUserGateway
        from app.application.dto.user import UserUpdateDTO

        session = AsyncMock()
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo_cls:
            mock_repo_cls.return_value.get_by_id = AsyncMock(return_value=None)
            maker = self._maker(session)
            gw = SqlAlchemyUserGateway(maker, MagicMock())
            res = await gw.update_user(uuid.uuid4(), UserUpdateDTO(email="x@x.com"))
            assert res is None

    @pytest.mark.asyncio
    async def test_update_user_payload_only_password(self):
        from app.adapters.persistence.user import SqlAlchemyUserGateway
        from app.application.dto.user import UserUpdateDTO
        from app.models.user import UserModel

        session = AsyncMock()
        model = UserModel(
            id=uuid.uuid4(),
            email="a@b.com",
            hashed_password="h",
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        with patch("app.adapters.persistence.user.UserRepository") as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.get_by_id = AsyncMock(return_value=model)
            repo.update = AsyncMock(return_value=model)
            hasher = MagicMock()
            hasher.hash.return_value = "hashed2"
            maker = self._maker(session)
            gw = SqlAlchemyUserGateway(maker, hasher)
            res = await gw.update_user(model.id, UserUpdateDTO(password="p2"))
            assert res is not None
            assert repo.update.call_args[0][1]["hashed_password"] == "hashed2"

    @pytest.mark.asyncio
    async def test_refresh_token_gateway(self):
        from app.adapters.persistence.user import SqlAlchemyRefreshTokenGateway

        session = AsyncMock()
        maker = self._maker(session)

        with patch(
            "app.adapters.persistence.user.RefreshTokenRepository"
        ) as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.get_user_id_by_hash = AsyncMock(return_value=uuid.uuid4())
            gw = SqlAlchemyRefreshTokenGateway(maker)
            res = await gw.get_by_hash("h")
            assert res is not None

        with patch(
            "app.adapters.persistence.user.RefreshTokenRepository"
        ) as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.create = AsyncMock(return_value=None)
            gw = SqlAlchemyRefreshTokenGateway(maker)
            await gw.create(uuid.uuid4(), "h", datetime.now(UTC))

        with patch(
            "app.adapters.persistence.user.RefreshTokenRepository"
        ) as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.rotate = AsyncMock(return_value=True)
            gw = SqlAlchemyRefreshTokenGateway(maker)
            res = await gw.rotate("old", uuid.uuid4(), "new", datetime.now(UTC))
            assert res is True

        with patch(
            "app.adapters.persistence.user.RefreshTokenRepository"
        ) as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.delete = AsyncMock(return_value=True)
            gw = SqlAlchemyRefreshTokenGateway(maker)
            res = await gw.delete("h")
            assert res is True

        with patch(
            "app.adapters.persistence.user.RefreshTokenRepository"
        ) as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.delete_by_user = AsyncMock(return_value=2)
            gw = SqlAlchemyRefreshTokenGateway(maker)
            res = await gw.delete_by_user(uuid.uuid4())
            assert res == 2

        with patch(
            "app.adapters.persistence.user.RefreshTokenRepository"
        ) as mock_repo_cls:
            repo = mock_repo_cls.return_value
            repo.delete_expired_by_user = AsyncMock(return_value=1)
            gw = SqlAlchemyRefreshTokenGateway(maker)
            res = await gw.delete_expired_by_user(uuid.uuid4())
            assert res == 1


# ---------------------------------------------------------------------------
# template_registry_service
# ---------------------------------------------------------------------------


class TestTemplateRegistryServiceBoost:
    @pytest.mark.asyncio
    async def test_create_duplicate_and_patch_conflict(self):
        from app.application.dto.template_registry import (
            RegistryCreateDTO,
            RegistryUpdateDTO,
        )
        from app.application.services.template_registry_service import (
            _REGISTRIES,
            TemplateRegistryService,
        )

        _REGISTRIES.clear()
        svc = TemplateRegistryService()
        dto = RegistryCreateDTO(owner="o", name="n")
        await svc.create_registry(dto)
        # duplicate create should raise
        with pytest.raises(Exception, match="already exists"):
            await svc.create_registry(dto)
        # create second registry with different owner/name
        dto2 = RegistryCreateDTO(owner="o2", name="n2")
        v2 = await svc.create_registry(dto2)
        # patch v2 to conflict with v1
        with pytest.raises(Exception, match="already exists"):
            await svc.patch_registry(v2.id, RegistryUpdateDTO(owner="o", name="n"))
        # patch success with branch update
        updated = await svc.patch_registry(
            v2.id, RegistryUpdateDTO(owner="o3", name="n3", default_branch="dev")
        )
        assert updated.owner == "o3"
        assert updated.default_branch == "dev"
        # patch with only branch change (owner/name unchanged)
        updated2 = await svc.patch_registry(
            v2.id, RegistryUpdateDTO(default_branch="main2")
        )
        assert updated2.default_branch == "main2"
        # patch not found
        with pytest.raises(Exception, match="not found"):
            await svc.patch_registry(uuid.uuid4(), RegistryUpdateDTO(owner="x"))
        # get not found
        with pytest.raises(Exception):
            await svc.get_registry(uuid.uuid4())
        # sync not found
        with pytest.raises(Exception):
            await svc.sync_registry(uuid.uuid4())
        # delete not found
        with pytest.raises(Exception):
            await svc.delete_registry(uuid.uuid4())
        # list pagination
        page = await svc.list_registries(offset=0, limit=10)
        assert page.total == 2
        page2 = await svc.list_registries(offset=10, limit=10)
        assert len(page2.items) == 0
        _REGISTRIES.clear()


# ---------------------------------------------------------------------------
# apscheduler_runtime
# ---------------------------------------------------------------------------


class TestApschedulerRuntimeBoost:
    def test_record_scheduler_event_misfire(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        sched = datetime.now(UTC)
        ev = JobExecutionEvent(EVENT_JOB_MISSED, "job", "default", sched)
        # should inc misfire and log
        ApschedulerRuntime._record_scheduler_event(ev)

    def test_record_scheduler_event_overlap(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        sched = datetime.now(UTC)
        ev = JobSubmissionEvent(EVENT_JOB_MAX_INSTANCES, "job", "default", [sched])
        ApschedulerRuntime._record_scheduler_event(ev)

    def test_record_scheduler_event_other(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        # JobExecutionEvent but not misfire -> should return early via second check
        ev = JobExecutionEvent(
            EVENT_JOB_MAX_INSTANCES, "job", "default", datetime.now(UTC)
        )
        # Not misfire and not JobSubmissionEvent -> early return
        ApschedulerRuntime._record_scheduler_event(ev)

        # Also test with non JobSubmissionEvent after misfire check?
        # Pass an object that is not JobExecutionEvent nor JobSubmissionEvent
        class Dummy:
            pass

        # Should return at isinstance JobSubmissionEvent check
        ApschedulerRuntime._record_scheduler_event(Dummy())  # type: ignore[arg-type]

    def test_owns_execution_and_mark_restored(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        assert rt.owns_execution is True
        rt.mark_restored(failed=0)
        assert rt.ready is True
        rt.mark_restored(failed=1)
        assert rt.ready is False
        # with ownership port
        mock_owner = MagicMock()
        mock_owner.is_acquired = False
        rt2 = ApschedulerRuntime(ownership=mock_owner)
        assert rt2.owns_execution is False
        mock_owner.is_acquired = True
        assert rt2.owns_execution is True
        rt2.configure_ownership(mock_owner)
        assert rt2._ownership is mock_owner
        rt2.configure_executor(AsyncMock())
        assert rt2._executor is not None
        rt2.configure_reconciler(AsyncMock())
        assert rt2._reconciler is not None

    @pytest.mark.asyncio
    async def test_start_reconciliation(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        # no reconciler -> should not create task
        rt.start_reconciliation()
        assert rt._reconciliation_task is None
        # with reconciler
        rt.configure_reconciler(AsyncMock(return_value=(0, 0)))
        rt.start_reconciliation(interval_seconds=10)
        assert rt._reconciliation_task is not None
        # second call should not create second task
        task_before = rt._reconciliation_task
        rt.start_reconciliation()
        assert rt._reconciliation_task is task_before
        await rt.stop()
        assert rt._reconciliation_task is None

    @pytest.mark.asyncio
    async def test_reconcile_loop_no_reconciler(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        # reconciler is None -> should raise RuntimeError then mark failed and continue until CancelledError
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt._reconcile_loop(0.01)
        assert rt.ready is False

    @pytest.mark.asyncio
    async def test_reconcile_loop_success_and_exception(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        rt.configure_reconciler(AsyncMock(return_value=(2, 0)))
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt._reconcile_loop(0.01)
        assert rt.ready is True

        rt2 = ApschedulerRuntime()
        rt2.configure_reconciler(AsyncMock(side_effect=RuntimeError("db")))
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt2._reconcile_loop(0.01)
        assert rt2.ready is False

    @pytest.mark.asyncio
    async def test_acquire_ownership_with_port(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        mock_owner = AsyncMock()
        mock_owner.try_acquire = AsyncMock(return_value=True)
        rt = ApschedulerRuntime(ownership=mock_owner)
        res = await rt.acquire_ownership()
        assert res is True
        assert rt._owns_execution is True
        mock_owner.try_acquire.return_value = False
        res2 = await rt.acquire_ownership()
        assert res2 is False

    @pytest.mark.asyncio
    async def test_acquire_ownership_engine_none(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        res = await rt.acquire_ownership(engine=None)
        assert res is True
        assert rt._owns_execution is True

    @pytest.mark.asyncio
    async def test_acquire_ownership_non_postgres(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        engine = MagicMock()
        engine.dialect.name = "sqlite"
        res = await rt.acquire_ownership(engine)
        assert res is True
        assert rt._owns_execution is True

    @pytest.mark.asyncio
    async def test_acquire_ownership_postgres_acquired_and_rejected(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        conn = AsyncMock()
        conn.scalar.return_value = True
        engine.connect = AsyncMock(return_value=conn)
        res = await rt.acquire_ownership(engine)
        assert res is True
        assert rt._owner_connection is conn
        await rt.stop()  # cleanup unlock path

        rt2 = ApschedulerRuntime()
        engine2 = MagicMock()
        engine2.dialect.name = "postgresql"
        conn2 = AsyncMock()
        conn2.scalar.return_value = False
        engine2.connect = AsyncMock(return_value=conn2)
        res2 = await rt2.acquire_ownership(engine2)
        assert res2 is False
        conn2.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_ownership_monitor(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        # with ownership port, is_postgres false -> no task
        mock_owner = MagicMock()
        mock_owner.is_postgres = False
        mock_owner.is_acquired = True
        rt = ApschedulerRuntime(ownership=mock_owner)
        rt.start_ownership_monitor()
        assert rt._ownership_task is None
        # is_postgres true -> task created
        mock_owner2 = MagicMock()
        mock_owner2.is_postgres = True
        mock_owner2.is_acquired = True
        mock_owner2.probe = AsyncMock(return_value=True)
        rt2 = ApschedulerRuntime(ownership=mock_owner2)
        rt2.start_ownership_monitor()
        assert rt2._ownership_task is not None
        await rt2.stop()
        # already has task -> second call does nothing
        mock_owner3 = MagicMock()
        mock_owner3.is_postgres = True
        rt3 = ApschedulerRuntime(ownership=mock_owner3)
        rt3._ownership_task = AsyncMock()
        rt3.start_ownership_monitor()
        # should remain same mocked task
        assert rt3._ownership_task is not None
        rt3._ownership_task = None  # cleanup

        # legacy path engine None -> no task
        rt4 = ApschedulerRuntime()
        rt4.start_ownership_monitor(engine=None)
        assert rt4._ownership_task is None
        # non postgres
        eng = MagicMock()
        eng.dialect.name = "sqlite"
        rt4.start_ownership_monitor(engine=eng)
        assert rt4._ownership_task is None
        # postgres -> task
        eng2 = MagicMock()
        eng2.dialect.name = "postgresql"
        rt4.start_ownership_monitor(engine=eng2)
        assert rt4._ownership_task is not None
        await rt4.stop()
        # already has task
        rt4._ownership_task = AsyncMock()
        rt4.start_ownership_monitor(engine=eng2)
        rt4._ownership_task = None

    @pytest.mark.asyncio
    async def test_monitor_ownership_with_port(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        # missing ownership -> RuntimeError
        rt = ApschedulerRuntime()
        with pytest.raises(RuntimeError):
            await rt._monitor_ownership_with_port()

        # not acquired -> try acquire
        mock_owner = AsyncMock()
        mock_owner.is_acquired = False
        mock_owner.try_acquire = AsyncMock(return_value=True)
        mock_owner.probe = AsyncMock(return_value=True)
        rt2 = ApschedulerRuntime(ownership=mock_owner)
        rt2.acquire_ownership = AsyncMock(return_value=True)  # type: ignore[attr-defined]
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt2._monitor_ownership_with_port()
        # acquired and probe ok
        mock_owner2 = AsyncMock()
        mock_owner2.is_acquired = True
        mock_owner2.probe = AsyncMock(return_value=True)
        rt3 = ApschedulerRuntime(ownership=mock_owner2)
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt3._monitor_ownership_with_port()
        # probe fails -> raises and logs, sets owns false
        mock_owner3 = AsyncMock()
        mock_owner3.is_acquired = True
        mock_owner3.probe = AsyncMock(return_value=False)
        rt4 = ApschedulerRuntime(ownership=mock_owner3)
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=[None, asyncio.CancelledError]),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt4._monitor_ownership_with_port()
        # exception path
        mock_owner4 = MagicMock()
        mock_owner4.is_acquired = True
        mock_owner4.probe = AsyncMock(side_effect=RuntimeError("probe err"))
        rt5 = ApschedulerRuntime(ownership=mock_owner4)
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt5._monitor_ownership_with_port()
        assert rt5._owns_execution is False

    @pytest.mark.asyncio
    async def test_monitor_ownership_legacy(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        # with owner_connection None -> acquire
        rt = ApschedulerRuntime()
        rt._owner_connection = None
        eng = MagicMock()
        eng.dialect.name = "postgresql"
        rt.acquire_ownership = AsyncMock(return_value=True)  # type: ignore[attr-defined]
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt._monitor_ownership(eng)
        # with connection execute success
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        rt2 = ApschedulerRuntime()
        rt2._owner_connection = conn
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt2._monitor_ownership(eng)
        # exception handling -> clears connection
        conn2 = AsyncMock()
        conn2.execute = AsyncMock(side_effect=RuntimeError("lost"))
        conn2.close = AsyncMock()
        rt3 = ApschedulerRuntime()
        rt3._owner_connection = conn2
        with patch(
            "app.adapters.runtime.apscheduler_runtime.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await rt3._monitor_ownership(eng)
        assert rt3._owner_connection is None
        assert rt3._owns_execution is False

    @pytest.mark.asyncio
    async def test_stop(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        # scheduler running false, with ownership port release
        mock_owner = AsyncMock()
        mock_owner.release = AsyncMock(return_value=None)
        mock_owner.is_acquired = True
        mock_owner.is_postgres = True
        rt = ApschedulerRuntime(ownership=mock_owner)
        # mock scheduler as not running
        rt._scheduler = MagicMock(running=False, shutdown=MagicMock())
        rt._reconciliation_task = asyncio.create_task(asyncio.sleep(10))
        rt._ownership_task = asyncio.create_task(asyncio.sleep(10))
        await asyncio.sleep(0)  # let tasks start
        await rt.stop()
        assert rt._reconciliation_task is None
        assert rt._ownership_task is None
        mock_owner.release.assert_awaited_once()

        # ownership release exception
        mock_owner2 = AsyncMock()
        mock_owner2.release = AsyncMock(side_effect=RuntimeError("fail"))
        rt2 = ApschedulerRuntime(ownership=mock_owner2)
        rt2._scheduler = MagicMock(running=False, shutdown=MagicMock())
        await rt2.stop()

        # legacy owner_connection with unlock and close success
        rt3 = ApschedulerRuntime()
        conn = AsyncMock()
        conn.execute = AsyncMock(return_value=None)
        conn.close = AsyncMock(return_value=None)
        rt3._owner_connection = conn
        rt3._scheduler = MagicMock(running=False, shutdown=MagicMock())
        await rt3.stop()
        conn.execute.assert_awaited_once()
        conn.close.assert_awaited_once()

        # legacy unlock exception and close exception
        rt4 = ApschedulerRuntime()
        conn2 = AsyncMock()
        conn2.execute = AsyncMock(side_effect=RuntimeError("unlock fail"))
        conn2.close = AsyncMock(side_effect=RuntimeError("close fail"))
        rt4._owner_connection = conn2
        rt4._scheduler = MagicMock(running=False, shutdown=MagicMock())
        await rt4.stop()

        # scheduler running true
        rt5 = ApschedulerRuntime()
        rt5._scheduler = MagicMock(running=True, shutdown=MagicMock())
        await rt5.stop()
        assert rt5.ready is False

        # stop with no ownership and no connection
        rt6 = ApschedulerRuntime()
        rt6._scheduler = MagicMock(running=False, shutdown=MagicMock())
        await rt6.stop()
        assert rt6._owns_execution is False

    @pytest.mark.asyncio
    async def test_schedule_and_execute(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        await rt.start()
        sid = uuid.uuid4()
        nid = uuid.uuid4()
        job_id = rt.schedule_script(sid, "0 9 * * *", [nid])
        assert job_id == str(sid)
        # schedule again should replace
        job_id2 = rt.schedule_script(sid, "0 10 * * *", [nid])
        assert job_id2 == str(sid)
        info = rt.get_schedule(sid)
        assert info is not None
        nxt = rt.get_next_run_time(sid)
        # next_run_time may be None or datetime depending on scheduler
        assert nxt is None or isinstance(nxt, datetime)
        lst = rt.list_schedules()
        assert any(j["job_id"] == str(sid) for j in lst)
        # unschedule
        assert rt.unschedule_script(sid) is True
        assert rt.unschedule_script(uuid.uuid4()) is False
        assert rt.get_schedule(uuid.uuid4()) is None
        assert rt.get_next_run_time(uuid.uuid4()) is None
        # list after removal
        assert rt.list_schedules() == []
        await rt.stop()

        # execute with owns false
        rt2 = ApschedulerRuntime()
        rt2.configure_executor(AsyncMock())
        rt2._owns_execution = False
        await rt2._execute_scheduled_script(uuid.uuid4(), [uuid.uuid4()])
        rt2._executor.assert_not_awaited()  # type: ignore[attr-defined]

        # execute with no executor -> RuntimeError
        rt3 = ApschedulerRuntime()
        rt3._owns_execution = True
        with pytest.raises(RuntimeError):
            await rt3._execute_scheduled_script(uuid.uuid4(), [uuid.uuid4()])

        # execute success and failure
        rt4 = ApschedulerRuntime()
        mock_exec = AsyncMock(return_value=None)
        rt4.configure_executor(mock_exec)
        rt4._owns_execution = True
        await rt4._execute_scheduled_script(
            uuid.uuid4(), [uuid.uuid4()], params={"a": 1}
        )
        mock_exec.assert_awaited_once()

        rt5 = ApschedulerRuntime()
        rt5.configure_executor(AsyncMock(side_effect=ValueError("fail")))
        rt5._owns_execution = True
        with pytest.raises(ValueError):
            await rt5._execute_scheduled_script(uuid.uuid4(), [uuid.uuid4()])

        # schedule with params and timezone and callback
        rt6 = ApschedulerRuntime()
        await rt6.start()
        cb = AsyncMock()
        sid2 = uuid.uuid4()
        rt6.schedule_script(
            sid2,
            "0 9 * * *",
            [uuid.uuid4()],
            callback=cb,
            params={"x": 1},
            timezone="UTC",
            misfire_grace_seconds=30,
            schedule_id=uuid.uuid4(),
        )
        assert rt6.get_schedule(sid2) is not None
        # get_next_run_time with job having next_run_time
        job = rt6._scheduler.get_job(str(sid2))
        if job:
            job.next_run_time = datetime.now(UTC)
            assert rt6.get_next_run_time(sid2) is not None
        # list schedules with next_run_time str
        lst2 = rt6.list_schedules()
        assert len(lst2) >= 1
        await rt6.stop()

    def test_get_next_run_time_non_datetime(self):
        from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime

        rt = ApschedulerRuntime()
        sid = uuid.uuid4()
        rt.schedule_script(sid, "0 9 * * *", [])
        job = rt._scheduler.get_job(str(sid))
        job.next_run_time = "not datetime"  # type: ignore[assignment]
        assert rt.get_next_run_time(sid) is None
        # also when job is None
        assert rt.get_next_run_time(uuid.uuid4()) is None
        # get_schedule when next_run is None
        job.next_run_time = None
        info2 = rt.get_schedule(sid)
        assert info2 is not None
        assert info2["next_run_time"] is None
        # list with none
        lst = rt.list_schedules()
        assert any(j["next_run_time"] is None for j in lst)
