"""Coverage tests for template_pack, user and favorite application services.

Patterns: mocked gateways (AsyncMock readers/writers), no live infra.
Template services are DB-backed (isolated SQLite per test).
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

from app.adapters.persistence.template_pack import (
    _unique_name,
    sanitize_tar_name,
    validate_asset_path,
    validate_pack_id,
)
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
from app.application.services.template_pack_service import TemplatePackService
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


def _cmd(name: str, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": name, "command": f"echo {name}"}
    payload.update(over)
    return payload


def _scr(name: str, **over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "steps": [{"label": "run", "type": "inline", "command": f"echo {name}"}],
    }
    payload.update(over)
    return payload


# ---------------------------------------------------------------- helpers


class TestTemplateHelpers:
    def test_unique_name_free(self) -> None:
        assert _unique_name("cmd", set()) == "cmd"

    def test_unique_name_collision(self) -> None:
        assert _unique_name("cmd", {"cmd"}) == "cmd_1"
        assert _unique_name("cmd", {"cmd", "cmd_1", "cmd_2"}) == "cmd_3"

    def test_validate_pack_id_ok(self) -> None:
        assert validate_pack_id("docker-install") == "docker-install"

    def test_validate_pack_id_bad(self) -> None:
        for bad in ("", "../x", "a/b", "has space", "x" * 101):
            with pytest.raises(DomainError):
                validate_pack_id(bad)

    def test_validate_asset_path_ok(self) -> None:
        assert validate_asset_path("assets/a.txt") == "assets/a.txt"

    def test_validate_asset_path_bad(self) -> None:
        for bad in ("", "/abs", "../up", "a/../b", "a//b", "a\\b", "a/./b"):
            with pytest.raises(DomainError):
                validate_asset_path(bad)

    def test_sanitize_tar_name(self) -> None:
        assert sanitize_tar_name("assets/a.txt") == "assets/a.txt"
        assert sanitize_tar_name("../evil") is None
        assert sanitize_tar_name("/abs") is None


# ---------------------------------------------------------------- create


class TestTemplateCreate:
    async def test_create_no_assets(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        assert detail.pack.name == "Pack"
        assert detail.assets == ()
        assert (await pack_service.get_pack_detail(detail.pack.id)).pack.id == (
            detail.pack.id
        )

    async def test_create_with_assets(
        self, pack_service: TemplatePackService
    ) -> None:
        data = _create(
            assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hello")),)
        )
        detail = await pack_service.create_pack(data)
        assert len(detail.assets) == 1
        assert detail.assets[0].size == 5
        tar = await pack_service.get_assets_tar(detail.pack.id)
        assert b"hello" in tar

    async def test_create_duplicate_same_registry(
        self, pack_service: TemplatePackService
    ) -> None:
        manifest = _manifest(pack_id="dup")
        reg = uuid.uuid4()
        await pack_service.create_pack(_create(manifest=manifest, registry_id=reg))
        with pytest.raises(PackConflictError, match="already exists"):
            await pack_service.create_pack(_create(manifest=manifest, registry_id=reg))

    async def test_create_same_pack_id_different_registry_ok(
        self, pack_service: TemplatePackService
    ) -> None:
        manifest = _manifest(pack_id="shared")
        await pack_service.create_pack(
            _create(manifest=manifest, registry_id=uuid.uuid4())
        )
        detail = await pack_service.create_pack(
            _create(manifest=manifest, registry_id=uuid.uuid4())
        )
        assert detail.pack.pack_id == "shared"
        # same pack_id with None registry twice is duplicate (partial unique index)
        m2 = _manifest(pack_id="samenone")
        await pack_service.create_pack(_create(manifest=m2, registry_id=None))
        with pytest.raises(PackConflictError):
            await pack_service.create_pack(_create(manifest=m2, registry_id=None))

    async def test_create_invalid_base64(
        self, pack_service: TemplatePackService
    ) -> None:
        data = _create(assets=(PackAssetCreateDTO(path="a.txt", content_base64="!!!"),))
        with pytest.raises(DomainError, match="Invalid base64"):
            await pack_service.create_pack(data)

    async def test_create_with_pydantic_commands(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(commands=(_manifest(),), scripts=(_manifest(),))
        )
        assert len(detail.commands) == 1

    async def test_create_bad_pack_id(
        self, pack_service: TemplatePackService
    ) -> None:
        with pytest.raises(DomainError):
            await pack_service.create_pack(_create(manifest=_manifest(pack_id="../x")))

    async def test_create_bad_asset_path(
        self, pack_service: TemplatePackService
    ) -> None:
        data = _create(
            assets=(PackAssetCreateDTO(path="../evil", content_base64=_b64("x")),)
        )
        with pytest.raises(DomainError):
            await pack_service.create_pack(data)

    async def test_create_duplicate_asset_path(
        self, pack_service: TemplatePackService
    ) -> None:
        data = _create(
            assets=(
                PackAssetCreateDTO(path="a.txt", content_base64=_b64("x")),
                PackAssetCreateDTO(path="a.txt", content_base64=_b64("y")),
            )
        )
        with pytest.raises(DomainError, match="Duplicate asset path"):
            await pack_service.create_pack(data)


# ---------------------------------------------------------------- list/get


class TestTemplateListGet:
    async def test_list_filters(self, pack_service: TemplatePackService) -> None:
        reg = uuid.uuid4()
        await pack_service.create_pack(
            _create(
                manifest=_manifest(
                    name="alpha-one", description="web server", tags=("web",)
                ),
                registry_id=reg,
            )
        )
        d2 = await pack_service.create_pack(
            _create(
                manifest=_manifest(name="beta", description="db thing", tags=("db",)),
                registry_id=uuid.uuid4(),
                commands=(_cmd("beta-cmd"),),
            )
        )
        # registry filter
        page = await pack_service.list_packs(PackListQueryDTO(registry_id=reg))
        assert page.total == 1
        # tag filter
        page = await pack_service.list_packs(PackListQueryDTO(tag="web"))
        assert page.total == 1
        page = await pack_service.list_packs(PackListQueryDTO(tag="missing"))
        assert page.total == 0
        # installed filters (none installed yet)
        assert (
            await pack_service.list_packs(PackListQueryDTO(installed=True))
        ).total == 0
        assert (
            await pack_service.list_packs(PackListQueryDTO(installed=False))
        ).total == 2
        # install one then re-check installed filters
        await pack_service.install_pack(d2.pack.id)
        assert (
            await pack_service.list_packs(PackListQueryDTO(installed=True))
        ).total == 1
        assert (
            await pack_service.list_packs(PackListQueryDTO(installed=False))
        ).total == 1
        # search by name (case-insensitive)
        page = await pack_service.list_packs(PackListQueryDTO(search="ALPHA"))
        assert page.total == 1
        # search by description
        page = await pack_service.list_packs(PackListQueryDTO(search="db thing"))
        assert page.total == 1
        # search no match
        assert (
            await pack_service.list_packs(PackListQueryDTO(search="zzz"))
        ).total == 0
        # search with None description pack
        await pack_service.create_pack(
            _create(manifest=_manifest(name="nodesc", description=None))
        )
        assert (
            await pack_service.list_packs(PackListQueryDTO(search="nodesc"))
        ).total == 1
        # pagination slice
        page = await pack_service.list_packs(PackListQueryDTO(offset=0, limit=1))
        assert len(page.items) == 1
        assert page.total >= 3

    async def test_get_detail_missing(self, pack_service: TemplatePackService) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.get_pack_detail(uuid.uuid4())

    async def test_get_view(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        view = await pack_service.get_pack_view(detail.pack.id)
        assert view.id == detail.pack.id
        with pytest.raises(PackNotFoundError):
            await pack_service.get_pack_view(uuid.uuid4())


# ---------------------------------------------------------------- tar


class TestTemplateTar:
    async def test_tar_empty(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        data = await pack_service.get_assets_tar(detail.pack.id)
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            assert tar.getnames() == []

    async def test_tar_with_assets(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(
            _create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hello")),)
            )
        )
        data = await pack_service.get_assets_tar(detail.pack.id)
        buf = io.BytesIO(data)
        with tarfile.open(fileobj=buf, mode="r") as tar:
            assert tar.getnames() == ["a.txt"]
            member = tar.extractfile("a.txt")
            assert member is not None
            assert member.read() == b"hello"

    async def test_tar_skips_unsafe_stored_path(
        self, pack_service: TemplatePackService
    ) -> None:
        # Unsafe paths cannot be created via API; sanitize_tar_name guards
        # legacy rows at archive build time.
        assert sanitize_tar_name("assets/ok.txt") == "assets/ok.txt"
        assert sanitize_tar_name("../../etc/passwd") is None

    async def test_tar_missing_pack(self, pack_service: TemplatePackService) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.get_assets_tar(uuid.uuid4())

    async def test_stream_alias(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        assert await pack_service.stream_assets_tar(detail.pack.id) == (
            await pack_service.get_assets_tar(detail.pack.id)
        )

    async def test_iterate_chunks(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(
            _create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hello")),)
            )
        )
        chunks = [c async for c in pack_service.iterate_assets_tar(detail.pack.id)]
        assert b"".join(chunks) == await pack_service.get_assets_tar(detail.pack.id)


# ---------------------------------------------------------------- install


class TestTemplateInstall:
    async def test_install_not_found(self, pack_service: TemplatePackService) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.install_pack(uuid.uuid4())

    async def test_install_empty(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        res = await pack_service.install_pack(detail.pack.id)
        assert res.total == 0
        assert res.succeeded == 0
        assert res.failed == 0

    async def test_install_success_commands_scripts(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(commands=(_cmd("c1"),), scripts=(_scr("s1"),))
        )
        res = await pack_service.install_pack(detail.pack.id)
        assert res.succeeded == 2
        assert res.failed == 0
        assert all(r.entity_id is not None for r in res.results)
        # installed info set
        updated = await pack_service.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version == "1.0.0"
        # installations recorded
        page = await pack_service.list_installations(detail.pack.id, 0, 10)
        assert page.total == 2

    async def test_install_already_installed(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(_create(commands=(_cmd("c1"),)))
        await pack_service.install_pack(detail.pack.id)
        with pytest.raises(PackConflictError, match="already installed"):
            await pack_service.install_pack(detail.pack.id)

    async def test_install_command_conflict_fail(
        self, pack_service: TemplatePackService
    ) -> None:
        d1 = await pack_service.create_pack(_create(commands=(_cmd("dup"),)))
        await pack_service.install_pack(d1.pack.id)
        d2 = await pack_service.create_pack(_create(commands=(_cmd("dup"),)))
        with pytest.raises(PackConflictError, match="Command name"):
            await pack_service.install_pack(d2.pack.id, on_conflict="fail")
        # nothing was persisted for the conflicting pack
        assert (
            await pack_service.get_pack_detail(d2.pack.id)
        ).pack.installed_version is None
        assert (await pack_service.list_installations(d2.pack.id, 0, 10)).total == 0

    async def test_install_script_conflict_fail(
        self, pack_service: TemplatePackService
    ) -> None:
        d1 = await pack_service.create_pack(_create(scripts=(_scr("dup"),)))
        await pack_service.install_pack(d1.pack.id)
        d2 = await pack_service.create_pack(_create(scripts=(_scr("dup"),)))
        with pytest.raises(PackConflictError, match="Script name"):
            await pack_service.install_pack(d2.pack.id, on_conflict="fail")

    async def test_install_rename_and_intra_pack_dup(
        self, pack_service: TemplatePackService
    ) -> None:
        d1 = await pack_service.create_pack(_create(commands=(_cmd("cmd"),)))
        await pack_service.install_pack(d1.pack.id)
        d2 = await pack_service.create_pack(
            _create(commands=(_cmd("cmd"), _cmd("cmd")))
        )
        res = await pack_service.install_pack(d2.pack.id, on_conflict="rename")
        assert res.succeeded == 2
        names = [r.name for r in res.results]
        assert "cmd_1" in names
        assert "cmd_2" in names

    async def test_install_script_rename(
        self, pack_service: TemplatePackService
    ) -> None:
        d1 = await pack_service.create_pack(_create(scripts=(_scr("s"),)))
        await pack_service.install_pack(d1.pack.id)
        d2 = await pack_service.create_pack(_create(scripts=(_scr("s"),)))
        res = await pack_service.install_pack(d2.pack.id, on_conflict="rename")
        assert res.succeeded == 1
        assert res.results[0].name == "s_1"

    async def test_install_partial_failure_bad_payload(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(
                commands=(_cmd("good"), {"name": "bad-cmd", "command": ""}),
                scripts=(_scr("ok-script"), {"name": "bad-script", "steps": []}),
            )
        )
        res = await pack_service.install_pack(detail.pack.id)
        assert res.total == 4
        assert res.succeeded == 2
        assert res.failed == 2
        assert all(r.error for r in res.results if r.status == "error")
        # still marks installed since at least one succeeded
        updated = await pack_service.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version is not None

    async def test_install_all_fail_no_installed_update(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(commands=({"name": "bad-only", "command": ""},))
        )
        res = await pack_service.install_pack(detail.pack.id)
        assert res.succeeded == 0
        assert res.failed == 1
        updated = await pack_service.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version is None

    async def test_install_with_model_dump_payloads(
        self, pack_service: TemplatePackService
    ) -> None:
        cmd = SimpleNamespace(
            name="m1", model_dump=lambda: {"name": "m1", "command": "echo m1"}
        )
        scr = SimpleNamespace(
            name="ms1",
            model_dump=lambda: {
                "name": "ms1",
                "steps": [{"label": "run", "type": "inline"}],
            },
        )
        detail = await pack_service.create_pack(
            _create(commands=(cmd,), scripts=(scr,))
        )
        res = await pack_service.install_pack(detail.pack.id)
        assert res.succeeded == 2

    async def test_install_errors_are_sanitized(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(commands=({"name": "bad-x", "command": ""},))
        )
        res = await pack_service.install_pack(detail.pack.id)
        assert res.failed == 1
        assert "Traceback" not in res.results[0].error

    async def test_install_actually_creates_rows(
        self, pack_service: TemplatePackService
    ) -> None:
        # Created rows are real: a second pack cannot reuse the name in fail mode.
        d1 = await pack_service.create_pack(_create(commands=(_cmd("real"),)))
        res = await pack_service.install_pack(d1.pack.id)
        assert res.results[0].entity_id is not None
        d2 = await pack_service.create_pack(_create(commands=(_cmd("real"),)))
        with pytest.raises(PackConflictError):
            await pack_service.install_pack(d2.pack.id)


# ---------------------------------------------------------------- uninstall/update


class TestTemplateUninstallUpdate:
    async def test_uninstall_not_found(self, pack_service: TemplatePackService) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.uninstall_pack(uuid.uuid4())

    async def test_uninstall_installed_removes_rows(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(commands=(_cmd("c1"),), scripts=(_scr("s1"),))
        )
        await pack_service.install_pack(detail.pack.id)
        await pack_service.uninstall_pack(detail.pack.id)
        updated = await pack_service.get_pack_detail(detail.pack.id)
        assert updated.pack.installed_version is None
        assert (await pack_service.list_installations(detail.pack.id, 0, 10)).total == 0
        # reinstall with same names works after removal
        res = await pack_service.install_pack(detail.pack.id)
        assert res.succeeded == 2

    async def test_uninstall_removes_created_rows(
        self, pack_service: TemplatePackService
    ) -> None:
        # After uninstall the names are free for an unrelated pack.
        detail = await pack_service.create_pack(_create(commands=(_cmd("gone"),)))
        await pack_service.install_pack(detail.pack.id)
        await pack_service.uninstall_pack(detail.pack.id)
        other = await pack_service.create_pack(_create(commands=(_cmd("gone"),)))
        res = await pack_service.install_pack(other.pack.id)
        assert res.succeeded == 1

    async def test_uninstall_not_installed(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(_create())
        await pack_service.uninstall_pack(detail.pack.id)  # no error
        assert (await pack_service.list_installations(detail.pack.id, 0, 10)).total == 0

    async def test_update_pack_not_found(
        self, pack_service: TemplatePackService
    ) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.update_pack(uuid.uuid4())

    async def test_update_pack_reinstall(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(_create(commands=(_cmd("c1"),)))
        await pack_service.install_pack(detail.pack.id)
        res = await pack_service.update_pack(detail.pack.id)
        assert res.succeeded == 1
        assert (await pack_service.list_installations(detail.pack.id, 0, 10)).total == 1

    async def test_update_pack_not_installed(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(_create(commands=(_cmd("c1"),)))
        res = await pack_service.update_pack(detail.pack.id, on_conflict="rename")
        assert res.succeeded == 1


# ------------------------------------------------- installations/stats/patch/delete


class TestTemplateInstallationsStats:
    async def test_list_installations_not_found(
        self, pack_service: TemplatePackService
    ) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.list_installations(uuid.uuid4(), 0, 10)

    async def test_list_installations_pagination_sorted(
        self, pack_service: TemplatePackService
    ) -> None:
        detail = await pack_service.create_pack(
            _create(commands=(_cmd("a"), _cmd("b"), _cmd("c")))
        )
        await pack_service.install_pack(detail.pack.id)
        page = await pack_service.list_installations(detail.pack.id, 0, 2)
        assert page.total == 3
        assert len(page.items) == 2
        page2 = await pack_service.list_installations(detail.pack.id, 2, 10)
        assert len(page2.items) == 1
        empty = await pack_service.list_installations(detail.pack.id, 10, 10)
        assert empty.items == ()

    async def test_stats_no_group(self, pack_service: TemplatePackService) -> None:
        stats = await pack_service.get_stats(None)
        assert stats.total == 0
        assert stats.buckets == ()
        d = await pack_service.create_pack(_create(commands=(_cmd("x"),)))
        await pack_service.install_pack(d.pack.id)
        await pack_service.create_pack(_create())
        stats = await pack_service.get_stats(None)
        assert stats.total == 2
        assert stats.installed == 1
        assert stats.not_installed == 1

    async def test_stats_registry(self, pack_service: TemplatePackService) -> None:
        reg = uuid.uuid4()
        d1 = await pack_service.create_pack(
            _create(manifest=_manifest(), registry_id=reg, commands=(_cmd("c1"),))
        )
        await pack_service.install_pack(d1.pack.id)
        await pack_service.create_pack(_create(manifest=_manifest(), registry_id=None))
        stats = await pack_service.get_stats("registry_id")
        assert stats.total == 2
        by = {b.group: b for b in stats.buckets}
        assert by[str(reg)].installed == 1
        assert by["local"].total == 1

    async def test_stats_tag(self, pack_service: TemplatePackService) -> None:
        d1 = await pack_service.create_pack(
            _create(manifest=_manifest(tags=("web", "api")), commands=(_cmd("c1"),))
        )
        await pack_service.install_pack(d1.pack.id)
        await pack_service.create_pack(_create(manifest=_manifest(tags=())))
        stats = await pack_service.get_stats("tag")
        by = {b.group: b for b in stats.buckets}
        assert by["web"].total == 1
        assert by["web"].installed == 1
        assert by["untagged"].total == 1

    async def test_stats_installed(self, pack_service: TemplatePackService) -> None:
        d = await pack_service.create_pack(_create(commands=(_cmd("x"),)))
        await pack_service.install_pack(d.pack.id)
        await pack_service.create_pack(_create())
        stats = await pack_service.get_stats("installed")
        assert len(stats.buckets) == 2
        by = {b.group: b for b in stats.buckets}
        assert by["installed"].total == 1
        assert by["not_installed"].total == 1

    async def test_stats_version(self, pack_service: TemplatePackService) -> None:
        await pack_service.create_pack(_create(manifest=_manifest(version="1.0.0")))
        await pack_service.create_pack(_create(manifest=_manifest(version="2.0.0")))
        stats = await pack_service.get_stats("version")
        by = {b.group: b for b in stats.buckets}
        assert by["1.0.0"].total == 1
        assert by["2.0.0"].total == 1

    async def test_stats_invalid_group_by(
        self, pack_service: TemplatePackService
    ) -> None:
        await pack_service.create_pack(_create())
        with pytest.raises(DomainError, match="Invalid group_by"):
            await pack_service.get_stats("custom-group")

    async def test_patch_not_found(self, pack_service: TemplatePackService) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.patch_pack(uuid.uuid4(), PackUpdateDTO(name="x"))

    async def test_patch_no_changes(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        view = await pack_service.patch_pack(detail.pack.id, PackUpdateDTO())
        assert view.name == detail.pack.name
        assert view.version == detail.pack.version

    async def test_patch_all_fields(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(_create())
        view = await pack_service.patch_pack(
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

    async def test_delete_not_found(self, pack_service: TemplatePackService) -> None:
        with pytest.raises(PackNotFoundError):
            await pack_service.delete_pack(uuid.uuid4())

    async def test_delete_ok_cleans_up(self, pack_service: TemplatePackService) -> None:
        detail = await pack_service.create_pack(
            _create(
                assets=(PackAssetCreateDTO(path="a.txt", content_base64=_b64("hi")),),
                commands=(_cmd("c1"),),
                scripts=(_scr("s1"),),
            )
        )
        await pack_service.install_pack(detail.pack.id)
        await pack_service.delete_pack(detail.pack.id)
        with pytest.raises(PackNotFoundError):
            await pack_service.get_pack_detail(detail.pack.id)
        # created rows are gone: names are reusable by an unrelated pack
        other = await pack_service.create_pack(_create(commands=(_cmd("c1"),)))
        res = await pack_service.install_pack(other.pack.id)
        assert res.succeeded == 1


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
