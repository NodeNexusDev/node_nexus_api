"""Coverage tests for template_pack, user and favorite application services.

Patterns: mocked gateways (AsyncMock readers/writers), no live infra.
In-memory TemplatePackService state is reset per test.
"""

from __future__ import annotations

import base64
import io
import tarfile
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.application.dto.favorite import (
    FavoriteCreateDTO,
    FavoriteDTO,
    FavoriteUpdateDTO,
)
from app.application.dto.template_pack import (
    PackAssetCreateDTO,
    PackCreateDTO,
    PackListQueryDTO,
    PackManifestDTO,
    PackUpdateDTO,
)
from app.application.dto.user import UserUpdateDTO, UserViewDTO
from app.application.services.favorite_service import FavoriteService
from app.application.services.template_pack_service import (
    _ASSET_RAW,
    _COMMAND_NAMES,
    _INSTALLATION_NAMES,
    _INSTALLATIONS,
    _PACKS,
    _SCRIPT_NAMES,
    TemplatePackService,
    _extract_name,
    _extract_raw_payload,
    _unique_name,
)
from app.application.services.user_service import UserService
from app.core.exceptions import (
    DomainError,
    FavoriteNotFoundError,
    InsufficientPermissionsError,
    PackConflictError,
    PackNotFoundError,
    UserAlreadyExistsError,
    UserNotFoundError,
)


@pytest.fixture(autouse=True)
def _clean_template_state():
    _PACKS.clear()
    _INSTALLATIONS.clear()
    _ASSET_RAW.clear()
    _INSTALLATION_NAMES.clear()
    _COMMAND_NAMES.clear()
    _SCRIPT_NAMES.clear()
    yield
    _PACKS.clear()
    _INSTALLATIONS.clear()
    _ASSET_RAW.clear()
    _INSTALLATION_NAMES.clear()
    _COMMAND_NAMES.clear()
    _SCRIPT_NAMES.clear()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _manifest(**over) -> PackManifestDTO:
    base: dict[str, Any] = {
        "pack_id": f"pack-{uuid.uuid4().hex[:8]}",
        "name": "Pack",
        "version": "1.0.0",
        "description": "desc",
        "author": "author",
        "tags": ("web",),
        "manifest_sha": "sha",
    }
    base.update(over)
    return PackManifestDTO(**base)


def _create(**over) -> PackCreateDTO:
    base: dict[str, Any] = {"manifest": _manifest()}
    base.update(over)
    return PackCreateDTO(**base)


def _user_view(**overrides) -> UserViewDTO:
    defaults = {
        "id": uuid4(),
        "email": "test@example.com",
        "is_active": True,
        "is_superuser": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return UserViewDTO(**defaults)


def _fav_dto(**overrides) -> FavoriteDTO:
    defaults = {
        "id": uuid4(),
        "target_type": "command",
        "target_id": uuid4(),
        "name": None,
        "note": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return FavoriteDTO(**defaults)


# ---------------------------------------------------------------- helpers


class TestTemplateHelpers:
    def test_extract_name_dict(self) -> None:
        assert _extract_name({"name": "a"}, "fb") == "a"

    def test_extract_name_dict_fallback(self) -> None:
        assert _extract_name({}, "fb") == "fb"

    def test_extract_name_object(self) -> None:
        assert _extract_name(SimpleNamespace(name="n"), "fb") == "n"

    def test_extract_name_object_fallback(self) -> None:
        assert _extract_name(SimpleNamespace(), "fb") == "fb"

    def test_unique_name_free(self) -> None:
        assert _unique_name("cmd", set()) == "cmd"

    def test_unique_name_collision(self) -> None:
        assert _unique_name("cmd", {"cmd"}) == "cmd_1"
        assert _unique_name("cmd", {"cmd", "cmd_1", "cmd_2"}) == "cmd_3"

    def test_extract_raw_payload_dict(self) -> None:
        assert _extract_raw_payload({"name": "x"}) == {"name": "x"}

    def test_extract_raw_payload_model(self) -> None:
        obj = SimpleNamespace(model_dump=lambda: {"name": "y"})
        assert _extract_raw_payload(obj) == {"name": "y"}

    def test_extract_raw_payload_model_raises(self) -> None:
        def _boom():
            raise RuntimeError("boom")

        obj = SimpleNamespace(model_dump=_boom)
        assert _extract_raw_payload(obj) is None

    def test_extract_raw_payload_model_non_dict(self) -> None:
        obj = SimpleNamespace(model_dump=lambda: "not-a-dict")
        assert _extract_raw_payload(obj) is None

    def test_extract_raw_payload_no_dump(self) -> None:
        assert _extract_raw_payload(SimpleNamespace(name="z")) is None
        assert _extract_raw_payload("plain-string") is None


# ---------------------------------------------------------------- create


class TestTemplateCreate:
    async def test_create_no_assets(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        assert detail.pack.name == "Pack"
        assert detail.assets == ()
        assert detail.pack.id in _PACKS

    async def test_create_with_assets(self) -> None:
        svc = TemplatePackService()
        data = _create(
            assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hello")),)
        )
        detail = await svc.create_pack(data)
        assert len(detail.assets) == 1
        assert detail.assets[0].size == 5
        assert detail.pack.id in _ASSET_RAW

    async def test_create_duplicate_same_registry(self) -> None:
        svc = TemplatePackService()
        manifest = _manifest(pack_id="dup")
        reg = uuid.uuid4()
        await svc.create_pack(_create(manifest=manifest, registry_id=reg))
        with pytest.raises(DomainError, match="already exists"):
            await svc.create_pack(_create(manifest=manifest, registry_id=reg))

    async def test_create_same_pack_id_different_registry_ok(self) -> None:
        svc = TemplatePackService()
        manifest = _manifest(pack_id="shared")
        await svc.create_pack(_create(manifest=manifest, registry_id=uuid.uuid4()))
        detail = await svc.create_pack(
            _create(manifest=manifest, registry_id=uuid.uuid4())
        )
        assert detail.pack.pack_id == "shared"
        # also same pack_id with None registry twice is duplicate
        m2 = _manifest(pack_id="samenone")
        await svc.create_pack(_create(manifest=m2, registry_id=None))
        with pytest.raises(DomainError):
            await svc.create_pack(_create(manifest=m2, registry_id=None))

    async def test_create_invalid_base64(self) -> None:
        svc = TemplatePackService()
        data = _create(assets=(PackAssetCreateDTO(path="a.txt", content_base64="!!!"),))
        with pytest.raises(DomainError, match="Invalid base64"):
            await svc.create_pack(data)

    async def test_create_with_pydantic_commands(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(commands=(_manifest(),), scripts=(_manifest(),))
        )
        assert len(detail.commands) == 1


# ---------------------------------------------------------------- list/get


class TestTemplateListGet:
    async def test_list_filters(self) -> None:
        svc = TemplatePackService()
        reg = uuid.uuid4()
        await svc.create_pack(
            _create(
                manifest=_manifest(
                    name="alpha-one", description="web server", tags=("web",)
                ),
                registry_id=reg,
            )
        )
        d2 = await svc.create_pack(
            _create(
                manifest=_manifest(name="beta", description="db thing", tags=("db",)),
                registry_id=uuid.uuid4(),
                commands=({"name": "beta-cmd"},),
            )
        )
        # registry filter
        page = await svc.list_packs(PackListQueryDTO(registry_id=reg))
        assert page.total == 1
        # tag filter
        page = await svc.list_packs(PackListQueryDTO(tag="web"))
        assert page.total == 1
        page = await svc.list_packs(PackListQueryDTO(tag="missing"))
        assert page.total == 0
        # installed filters (none installed yet)
        assert (await svc.list_packs(PackListQueryDTO(installed=True))).total == 0
        assert (await svc.list_packs(PackListQueryDTO(installed=False))).total == 2
        # install one then re-check installed filters
        await svc.install_pack(d2.pack.id)
        assert (await svc.list_packs(PackListQueryDTO(installed=True))).total == 1
        assert (await svc.list_packs(PackListQueryDTO(installed=False))).total == 1
        # search by name (case-insensitive)
        page = await svc.list_packs(PackListQueryDTO(search="ALPHA"))
        assert page.total == 1
        # search by description
        page = await svc.list_packs(PackListQueryDTO(search="db thing"))
        assert page.total == 1
        # search no match
        assert (await svc.list_packs(PackListQueryDTO(search="zzz"))).total == 0
        # search with None description pack
        await svc.create_pack(
            _create(manifest=_manifest(name="nodesc", description=None))
        )
        assert (await svc.list_packs(PackListQueryDTO(search="nodesc"))).total == 1
        # pagination slice
        page = await svc.list_packs(PackListQueryDTO(offset=0, limit=1))
        assert len(page.items) == 1
        assert page.total >= 3

    async def test_get_detail_missing(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.get_pack_detail(uuid.uuid4())

    async def test_get_view(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        view = await svc.get_pack_view(detail.pack.id)
        assert view.id == detail.pack.id
        with pytest.raises(PackNotFoundError):
            await svc.get_pack_view(uuid.uuid4())


# ---------------------------------------------------------------- tar


class TestTemplateTar:
    async def test_tar_empty(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        data = await svc.get_assets_tar(detail.pack.id)
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            assert tar.getnames() == []

    async def test_tar_with_assets(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hello")),)
            )
        )
        data = await svc.get_assets_tar(detail.pack.id)
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            assert tar.getnames() == ["a.txt"]
            member = tar.extractfile("a.txt")
            assert member is not None
            assert member.read() == b"hello"

    async def test_tar_missing_raw_falls_back_empty(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hi")),)
            )
        )
        _ASSET_RAW.pop(detail.pack.id)
        data = await svc.get_assets_tar(detail.pack.id)
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            assert tar.getnames() == ["a.txt"]
            member = tar.extractfile("a.txt")
            assert member is not None
            assert member.read() == b""

    async def test_tar_missing_pack(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.get_assets_tar(uuid.uuid4())

    async def test_stream_alias(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        assert await svc.stream_assets_tar(detail.pack.id) == await svc.get_assets_tar(
            detail.pack.id
        )


# ---------------------------------------------------------------- install


class TestTemplateInstall:
    async def test_install_not_found(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.install_pack(uuid.uuid4())

    async def test_install_empty(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        res = await svc.install_pack(detail.pack.id)
        assert res.total == 0
        assert res.succeeded == 0
        assert res.failed == 0

    async def test_install_success_commands_scripts(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(commands=({"name": "c1"},), scripts=({"name": "s1"},))
        )
        res = await svc.install_pack(detail.pack.id)
        assert res.succeeded == 2
        assert res.failed == 0
        # installed info set
        updated = await svc.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version == "1.0.0"
        # installations recorded
        page = await svc.list_installations(detail.pack.id, 0, 10)
        assert page.total == 2

    async def test_install_already_installed(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create(commands=({"name": "c1"},)))
        await svc.install_pack(detail.pack.id)
        with pytest.raises(PackConflictError, match="already installed"):
            await svc.install_pack(detail.pack.id)

    async def test_install_command_conflict_fail(self) -> None:
        svc = TemplatePackService()
        d1 = await svc.create_pack(_create(commands=({"name": "dup"},)))
        await svc.install_pack(d1.pack.id)
        d2 = await svc.create_pack(_create(commands=({"name": "dup"},)))
        with pytest.raises(PackConflictError, match="Command name"):
            await svc.install_pack(d2.pack.id, on_conflict="fail")

    async def test_install_script_conflict_fail(self) -> None:
        svc = TemplatePackService()
        d1 = await svc.create_pack(_create(scripts=({"name": "dup"},)))
        await svc.install_pack(d1.pack.id)
        d2 = await svc.create_pack(_create(scripts=({"name": "dup"},)))
        with pytest.raises(PackConflictError, match="Script name"):
            await svc.install_pack(d2.pack.id, on_conflict="fail")

    async def test_install_rename_and_intra_pack_dup(self) -> None:
        svc = TemplatePackService()
        d1 = await svc.create_pack(_create(commands=({"name": "cmd"},)))
        await svc.install_pack(d1.pack.id)
        d2 = await svc.create_pack(_create(commands=({"name": "cmd"}, {"name": "cmd"})))
        res = await svc.install_pack(d2.pack.id, on_conflict="rename")
        assert res.succeeded == 2
        names = [r.name for r in res.results]
        assert "cmd_1" in names
        assert "cmd_2" in names

    async def test_install_script_rename(self) -> None:
        svc = TemplatePackService()
        d1 = await svc.create_pack(_create(scripts=({"name": "s"},)))
        await svc.install_pack(d1.pack.id)
        d2 = await svc.create_pack(_create(scripts=({"name": "s"},)))
        res = await svc.install_pack(d2.pack.id, on_conflict="rename")
        assert res.succeeded == 1
        assert res.results[0].name == "s_1"

    async def test_install_partial_failure_fail_substring(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(
                commands=({"name": "good"}, {"name": "will-fail-cmd"}),
                scripts=({"name": "ok-script"}, {"name": "fail-script"}),
            )
        )
        res = await svc.install_pack(detail.pack.id)
        assert res.total == 4
        assert res.succeeded == 2
        assert res.failed == 2
        assert all(r.status == "error" for r in res.results if "fail" in r.name.lower())
        # still marks installed since at least one succeeded
        updated = await svc.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version is not None

    async def test_install_all_fail_no_installed_update(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create(commands=({"name": "fail-only"},)))
        res = await svc.install_pack(detail.pack.id)
        assert res.succeeded == 0
        assert res.failed == 1
        updated = await svc.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version is None

    async def test_install_with_model_dump_payloads(self) -> None:
        svc = TemplatePackService()
        cmd = SimpleNamespace(name="m1", model_dump=lambda: {"name": "m1"})
        scr = SimpleNamespace(name="ms1", model_dump=lambda: {"name": "ms1"})
        detail = await svc.create_pack(_create(commands=(cmd,), scripts=(scr,)))
        res = await svc.install_pack(detail.pack.id)
        assert res.succeeded == 2

    async def test_install_model_dump_raises_goes_error_path(self) -> None:
        # model_dump raising is swallowed for payload but install still succeeds
        # (payload extraction failure does not fail install); use fail name for error
        svc = TemplatePackService()
        detail = await svc.create_pack(_create(commands=({"name": "fail-x"},)))
        res = await svc.install_pack(detail.pack.id)
        assert res.failed == 1


# ---------------------------------------------------------------- uninstall/update


class TestTemplateUninstallUpdate:
    async def test_uninstall_not_found(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.uninstall_pack(uuid.uuid4())

    async def test_uninstall_installed_releases_names(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(commands=({"name": "c1"},), scripts=({"name": "s1"},))
        )
        await svc.install_pack(detail.pack.id)
        assert "c1" in _COMMAND_NAMES
        await svc.uninstall_pack(detail.pack.id)
        assert "c1" not in _COMMAND_NAMES
        assert "s1" not in _SCRIPT_NAMES
        updated = await svc.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version is None
        # reinstall with same names works after release
        res = await svc.install_pack(detail.pack.id)
        assert res.succeeded == 2

    async def test_uninstall_not_installed(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        await svc.uninstall_pack(detail.pack.id)  # no error
        assert (
            detail.pack.id not in _INSTALLATIONS or _INSTALLATIONS[detail.pack.id] == []
        )

    async def test_update_pack_not_found(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.update_pack(uuid.uuid4())

    async def test_update_pack_reinstall(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create(commands=({"name": "c1"},)))
        await svc.install_pack(detail.pack.id)
        res = await svc.update_pack(detail.pack.id)
        assert res.succeeded == 1

    async def test_update_pack_not_installed(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create(commands=({"name": "c1"},)))
        res = await svc.update_pack(detail.pack.id, on_conflict="rename")
        assert res.succeeded == 1


# ------------------------------------------------- installations/stats/patch/delete


class TestTemplateInstallationsStats:
    async def test_list_installations_not_found(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.list_installations(uuid.uuid4(), 0, 10)

    async def test_list_installations_pagination_sorted(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(commands=({"name": "a"}, {"name": "b"}, {"name": "c"}))
        )
        await svc.install_pack(detail.pack.id)
        page = await svc.list_installations(detail.pack.id, 0, 2)
        assert page.total == 3
        assert len(page.items) == 2
        page2 = await svc.list_installations(detail.pack.id, 2, 10)
        assert len(page2.items) == 1
        empty = await svc.list_installations(detail.pack.id, 10, 10)
        assert empty.items == ()

    async def test_stats_no_group(self) -> None:
        svc = TemplatePackService()
        stats = await svc.get_stats(None)
        assert stats.total == 0
        assert stats.buckets == ()
        d = await svc.create_pack(_create(commands=({"name": "x"},)))
        await svc.install_pack(d.pack.id)
        await svc.create_pack(_create())
        stats = await svc.get_stats(None)
        assert stats.total == 2
        assert stats.installed == 1
        assert stats.not_installed == 1

    async def test_stats_registry(self) -> None:
        svc = TemplatePackService()
        reg = uuid.uuid4()
        d1 = await svc.create_pack(
            _create(manifest=_manifest(), registry_id=reg, commands=({"name": "c1"},))
        )
        await svc.install_pack(d1.pack.id)
        await svc.create_pack(_create(manifest=_manifest(), registry_id=None))
        stats = await svc.get_stats("registry_id")
        assert stats.total == 2
        by = {b.group: b for b in stats.buckets}
        assert by[str(reg)].installed == 1
        assert by["local"].total == 1

    async def test_stats_tag(self) -> None:
        svc = TemplatePackService()
        d1 = await svc.create_pack(
            _create(manifest=_manifest(tags=("web", "api")), commands=({"name": "c1"},))
        )
        await svc.install_pack(d1.pack.id)
        await svc.create_pack(_create(manifest=_manifest(tags=())))
        stats = await svc.get_stats("tag")
        by = {b.group: b for b in stats.buckets}
        assert by["web"].total == 1
        assert by["web"].installed == 1
        assert by["untagged"].total == 1

    async def test_stats_installed(self) -> None:
        svc = TemplatePackService()
        d = await svc.create_pack(_create(commands=({"name": "x"},)))
        await svc.install_pack(d.pack.id)
        await svc.create_pack(_create())
        stats = await svc.get_stats("installed")
        assert len(stats.buckets) == 2
        by = {b.group: b for b in stats.buckets}
        assert by["installed"].total == 1
        assert by["not_installed"].total == 1

    async def test_stats_version(self) -> None:
        svc = TemplatePackService()
        await svc.create_pack(_create(manifest=_manifest(version="1.0.0")))
        await svc.create_pack(_create(manifest=_manifest(version="2.0.0")))
        stats = await svc.get_stats("version")
        by = {b.group: b for b in stats.buckets}
        assert by["1.0.0"].total == 1
        assert by["2.0.0"].total == 1

    async def test_stats_generic(self) -> None:
        svc = TemplatePackService()
        await svc.create_pack(_create())
        stats = await svc.get_stats("custom-group")
        assert len(stats.buckets) == 1
        assert stats.buckets[0].group == "custom-group"

    async def test_patch_not_found(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.patch_pack(uuid.uuid4(), PackUpdateDTO(name="x"))

    async def test_patch_no_changes(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        view = await svc.patch_pack(detail.pack.id, PackUpdateDTO())
        assert view.name == detail.pack.name
        assert view.version == detail.pack.version

    async def test_patch_all_fields(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(_create())
        view = await svc.patch_pack(
            detail.pack.id,
            PackUpdateDTO(
                name="new",
                description="nd",
                version="9.9.9",
                author="bob",
                tags=("t1",),
                manifest_sha="newsha",
                readme="nr",
            ),
        )
        assert view.name == "new"
        assert view.description == "nd"
        assert view.version == "9.9.9"
        assert view.author == "bob"
        assert view.tags == ("t1",)
        assert view.manifest_sha == "newsha"
        assert view.readme == "nr"

    async def test_delete_not_found(self) -> None:
        svc = TemplatePackService()
        with pytest.raises(PackNotFoundError):
            await svc.delete_pack(uuid.uuid4())

    async def test_delete_ok_cleans_up(self) -> None:
        svc = TemplatePackService()
        detail = await svc.create_pack(
            _create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hi")),),
                commands=({"name": "c1"},),
                scripts=({"name": "s1"},),
            )
        )
        await svc.install_pack(detail.pack.id)
        await svc.delete_pack(detail.pack.id)
        assert detail.pack.id not in _PACKS
        assert detail.pack.id not in _ASSET_RAW
        assert detail.pack.id not in _INSTALLATIONS
        with pytest.raises(PackNotFoundError):
            await svc.get_pack_detail(detail.pack.id)


# ---------------------------------------------------------------- user service


class TestUserServiceCov:
    async def test_create_not_superuser(self) -> None:
        svc = UserService(reader=AsyncMock(), writer=AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.create_user("a@b.com", "pw", caller_is_superuser=False)

    async def test_create_duplicate(self) -> None:
        reader = AsyncMock()
        reader.get_by_email.return_value = _user_view()
        svc = UserService(reader=reader, writer=AsyncMock())
        with pytest.raises(UserAlreadyExistsError):
            await svc.create_user("a@b.com", "pw", caller_is_superuser=True)

    async def test_create_success(self) -> None:
        reader = AsyncMock()
        reader.get_by_email.return_value = None
        writer = AsyncMock()
        created = _user_view()
        writer.create_user.return_value = created
        svc = UserService(reader=reader, writer=writer)
        res = await svc.create_user("a@b.com", "pw", caller_is_superuser=True)
        assert res == created

    async def test_list_not_superuser(self) -> None:
        svc = UserService(reader=AsyncMock(), writer=AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.list_users(0, 10, caller_is_superuser=False)

    async def test_list_success(self) -> None:
        reader = AsyncMock()
        users = [_user_view(), _user_view(email="b@b.com")]
        reader.list_users.return_value = users
        reader.count_users.return_value = 2
        svc = UserService(reader=reader, writer=AsyncMock())
        page = await svc.list_users(0, 10, caller_is_superuser=True)
        assert page.total == 2
        assert page.items == tuple(users)

    async def test_get_not_superuser(self) -> None:
        svc = UserService(reader=AsyncMock(), writer=AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.get_user(uuid4(), caller_is_superuser=False)

    async def test_get_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_user.return_value = None
        svc = UserService(reader=reader, writer=AsyncMock())
        with pytest.raises(UserNotFoundError):
            await svc.get_user(uuid4(), caller_is_superuser=True)

    async def test_get_success(self) -> None:
        reader = AsyncMock()
        user = _user_view()
        reader.get_user.return_value = user
        svc = UserService(reader=reader, writer=AsyncMock())
        assert await svc.get_user(user.id, caller_is_superuser=True) == user

    async def test_patch_not_superuser(self) -> None:
        svc = UserService(reader=AsyncMock(), writer=AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.patch_user(uuid4(), UserUpdateDTO(), caller_is_superuser=False)

    async def test_patch_email_conflict(self) -> None:
        reader = AsyncMock()
        reader.get_by_email.return_value = _user_view(id=uuid4())
        svc = UserService(reader=reader, writer=AsyncMock())
        with pytest.raises(UserAlreadyExistsError):
            await svc.patch_user(
                uuid4(), UserUpdateDTO(email="taken@b.com"), caller_is_superuser=True
            )

    async def test_patch_email_same_id_ok(self) -> None:
        uid = uuid4()
        reader = AsyncMock()
        reader.get_by_email.return_value = _user_view(id=uid)
        writer = AsyncMock()
        updated = _user_view(id=uid)
        writer.update_user.return_value = updated
        svc = UserService(reader=reader, writer=writer)
        res = await svc.patch_user(
            uid, UserUpdateDTO(email="same@b.com"), caller_is_superuser=True
        )
        assert res == updated

    async def test_patch_email_none(self) -> None:
        reader = AsyncMock()
        writer = AsyncMock()
        updated = _user_view()
        writer.update_user.return_value = updated
        svc = UserService(reader=reader, writer=writer)
        res = await svc.patch_user(
            updated.id, UserUpdateDTO(is_active=False), caller_is_superuser=True
        )
        assert res == updated
        reader.get_by_email.assert_not_called()

    async def test_patch_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_by_email.return_value = None
        writer = AsyncMock()
        writer.update_user.return_value = None
        svc = UserService(reader=reader, writer=writer)
        with pytest.raises(UserNotFoundError):
            await svc.patch_user(
                uuid4(), UserUpdateDTO(email="n@b.com"), caller_is_superuser=True
            )

    async def test_patch_success(self) -> None:
        reader = AsyncMock()
        reader.get_by_email.return_value = None
        writer = AsyncMock()
        updated = _user_view()
        writer.update_user.return_value = updated
        svc = UserService(reader=reader, writer=writer)
        res = await svc.patch_user(
            updated.id, UserUpdateDTO(email="n@b.com"), caller_is_superuser=True
        )
        assert res == updated

    async def test_delete_not_superuser(self) -> None:
        svc = UserService(reader=AsyncMock(), writer=AsyncMock())
        with pytest.raises(InsufficientPermissionsError):
            await svc.delete_user(uuid4(), caller_is_superuser=False)

    async def test_delete_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_user.return_value = None
        svc = UserService(reader=reader, writer=AsyncMock())
        with pytest.raises(UserNotFoundError):
            await svc.delete_user(uuid4(), caller_is_superuser=True)

    async def test_delete_success(self) -> None:
        reader = AsyncMock()
        user = _user_view()
        reader.get_user.return_value = user
        writer = AsyncMock()
        writer.delete_user.return_value = True
        svc = UserService(reader=reader, writer=writer)
        assert await svc.delete_user(user.id, caller_is_superuser=True) is True


# ---------------------------------------------------------------- favorite service


class TestFavoriteServiceCov:
    async def test_list_defaults(self) -> None:
        reader = AsyncMock()
        reader.list_favorites.return_value = ([], 0)
        svc = FavoriteService(reader=reader, writer=AsyncMock())
        items, total = await svc.list_favorites()
        assert (items, total) == ([], 0)
        reader.list_favorites.assert_awaited_once_with(
            target_type=None, offset=0, limit=20
        )

    async def test_list_pagination(self) -> None:
        reader = AsyncMock()
        reader.list_favorites.return_value = ([], 0)
        svc = FavoriteService(reader=reader, writer=AsyncMock())
        await svc.list_favorites(target_type="command", page=3, size=5)
        reader.list_favorites.assert_awaited_once_with(
            target_type="command", offset=10, limit=5
        )

    async def test_add(self) -> None:
        writer = AsyncMock()
        expected = _fav_dto()
        writer.add_favorite.return_value = expected
        svc = FavoriteService(reader=AsyncMock(), writer=writer)
        data = FavoriteCreateDTO(target_type="command", target_id=uuid4())
        assert await svc.add_favorite(data) == expected
        writer.add_favorite.assert_awaited_once_with(data)

    async def test_get_success(self) -> None:
        reader = AsyncMock()
        expected = _fav_dto()
        reader.get_favorite.return_value = expected
        svc = FavoriteService(reader=reader, writer=AsyncMock())
        res = await svc.get_favorite("command", str(expected.target_id))
        assert res == expected

    async def test_get_not_found(self) -> None:
        reader = AsyncMock()
        reader.get_favorite.return_value = None
        svc = FavoriteService(reader=reader, writer=AsyncMock())
        with pytest.raises(FavoriteNotFoundError):
            await svc.get_favorite("command", str(uuid4()))

    async def test_update_success(self) -> None:
        writer = AsyncMock()
        expected = _fav_dto()
        writer.update_favorite.return_value = expected
        svc = FavoriteService(reader=AsyncMock(), writer=writer)
        res = await svc.update_favorite(
            "command", str(expected.target_id), FavoriteUpdateDTO(name="n")
        )
        assert res == expected

    async def test_update_not_found(self) -> None:
        writer = AsyncMock()
        writer.update_favorite.return_value = None
        svc = FavoriteService(reader=AsyncMock(), writer=writer)
        with pytest.raises(FavoriteNotFoundError):
            await svc.update_favorite(
                "command", str(uuid4()), FavoriteUpdateDTO(name="n")
            )

    async def test_remove_success(self) -> None:
        writer = AsyncMock()
        writer.remove_favorite.return_value = True
        svc = FavoriteService(reader=AsyncMock(), writer=writer)
        assert await svc.remove_favorite("command", str(uuid4())) is True

    async def test_remove_not_found(self) -> None:
        writer = AsyncMock()
        writer.remove_favorite.return_value = False
        svc = FavoriteService(reader=AsyncMock(), writer=writer)
        with pytest.raises(FavoriteNotFoundError):
            await svc.remove_favorite("command", str(uuid4()))
