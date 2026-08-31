"""Unit tests for new 2.0 code coverage.

Covers schemas, models, services, persistence, and API v2.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.api.error_mapping import domain_error_handler
from app.application.dto.compose import (
    ComposeCreateDTO,
    ComposeUpdateDTO,
    ComposeViewDTO,
)
from app.application.dto.docker import (
    ContainerRenameRequestDTO,
)
from app.application.dto.template_pack import (
    PackAssetCreateDTO,
    PackCreateDTO,
    PackListQueryDTO,
    PackManifestDTO,
)
from app.application.dto.template_registry import RegistryCreateDTO
from app.application.services.compose_service import (
    ComposeService,
    _compose_file_path,
    _env_prefix,
    _validate_project_name,
)
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.resource_service import DockerResourceService
from app.application.services.docker.system_service import DockerSystemService
from app.application.services.template_pack_service import TemplatePackService
from app.application.services.template_registry_service import TemplateRegistryService
from app.core.exceptions import (
    ComposeProjectAlreadyExistsError,
    ComposeProjectNotFoundError,
    DockerValidationError,
    DomainError,
)
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_compose_view(**overrides: object) -> ComposeViewDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "project_name": "myproj",
        "compose": "version: '3'\nservices:\n  web:\n    image: nginx",
        "env": {"FOO": "bar"},
        "template_pack_id": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return ComposeViewDTO(**defaults)  # type: ignore[arg-type]


def _mock_node(node_id: UUID | None = None) -> MagicMock:
    nid = node_id or uuid.uuid4()
    node = MagicMock()
    node.id = nid
    node.is_docker_available = True
    return node


# ---------------------------------------------------------------------------
# Schemas: compose, template_registry, template_pack (bulk, cursor, 207)
# ---------------------------------------------------------------------------


class TestComposeSchemas:
    def test_compose_create_valid(self) -> None:
        from app.schemas.compose import ComposeCreate

        m = ComposeCreate(project_name="proj1", compose="version: '3'")
        assert m.project_name == "proj1"
        assert m.compose == "version: '3'"

    def test_compose_create_invalid_empty(self) -> None:
        from app.schemas.compose import ComposeCreate

        with pytest.raises(ValidationError):
            ComposeCreate(project_name="", compose="x")

    def test_bulk_create_request_valid(self) -> None:
        from app.schemas.compose import BulkComposeCreateRequest, ComposeCreate

        req = BulkComposeCreateRequest(
            items=[ComposeCreate(project_name="a", compose="x")]
        )
        assert len(req.items) == 1

    def test_bulk_create_request_empty_fails(self) -> None:
        from app.schemas.compose import BulkComposeCreateRequest

        with pytest.raises(ValidationError):
            BulkComposeCreateRequest(items=[])

    def test_bulk_create_request_too_many(self) -> None:
        from app.schemas.compose import BulkComposeCreateRequest, ComposeCreate

        items = [ComposeCreate(project_name=f"p{i}", compose="x") for i in range(101)]
        with pytest.raises(ValidationError):
            BulkComposeCreateRequest(items=items)  # type: ignore[arg-type]

    def test_bulk_response_207_structure(self) -> None:
        from app.schemas.compose import BulkComposeResponse, BulkComposeResult

        r = BulkComposeResponse(
            total=2,
            succeeded=1,
            failed=1,
            results=[
                BulkComposeResult(project_name="a", status="success", id=uuid.uuid4()),
                BulkComposeResult(project_name="b", status="error", error="dup"),
            ],
        )
        assert r.total == 2
        assert r.failed == 1

    def test_cursor_page_generic(self) -> None:
        from app.schemas.common import CursorPage
        from app.schemas.compose import ComposeResponse

        now = datetime.now(UTC)
        item = ComposeResponse(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="p",
            compose="x",
            env=None,
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        page = CursorPage[ComposeResponse](
            items=[item], next_cursor=None, has_more=False, limit=20
        )
        assert len(page.items) == 1

    def test_bulk_result_envelope(self) -> None:
        from app.schemas.common import BulkResult
        from app.schemas.compose import BulkComposeResult

        bulk = BulkResult[BulkComposeResult](
            total=1,
            succeeded=1,
            failed=0,
            results=[BulkComposeResult(project_name="a", status="success")],
        )
        assert bulk.succeeded == 1

    def test_compose_up_request(self) -> None:
        from app.schemas.compose import ComposeUpRequest

        r = ComposeUpRequest(pull=True, build=False, services=["web"])
        assert r.pull is True

    def test_compose_down_request(self) -> None:
        from app.schemas.compose import ComposeDownRequest

        r = ComposeDownRequest(
            volumes=True, remove_orphans=True, timeout=30, images="all"
        )
        assert r.volumes is True

    def test_compose_kill_request(self) -> None:
        from app.schemas.compose import ComposeKillRequest

        r = ComposeKillRequest(signal="SIGKILL", services=["web"])
        assert r.signal == "SIGKILL"

    def test_compose_exec_request(self) -> None:
        from app.schemas.compose import ComposeExecRequest

        r = ComposeExecRequest(service="web", command="ls", timeout=30)
        assert r.service == "web"

    def test_compose_run_request(self) -> None:
        from app.schemas.compose import ComposeRunRequest

        r = ComposeRunRequest(service="web", command="echo hi", detached=True)
        assert r.detached is True

    def test_compose_schemas_bulk_delete(self) -> None:
        from app.schemas.compose import (
            BulkComposeDeleteRequest,
            BulkComposeUpdateItem,
            BulkComposeUpdateRequest,
            ComposeUpdate,
        )

        d = BulkComposeDeleteRequest(project_names=["a", "b"])
        assert len(d.project_names) == 2
        u = BulkComposeUpdateRequest(
            updates=[
                BulkComposeUpdateItem(
                    project_name="a", changes=ComposeUpdate(compose="new")
                )
            ]
        )
        assert u.updates[0].project_name == "a"

    def test_compose_response_from_attributes(self) -> None:
        from app.schemas.compose import ComposeResponse

        dto = _make_compose_view()
        resp = ComposeResponse(
            id=dto.id,
            node_id=dto.node_id,
            project_name=dto.project_name,
            compose=dto.compose,
            env=dto.env,
            template_pack_id=dto.template_pack_id,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )
        assert resp.project_name == dto.project_name


class TestTemplateRegistrySchemas:
    def test_registry_create_valid(self) -> None:
        from app.schemas.template_registry import RegistryCreate

        r = RegistryCreate(owner="octocat", name="my-repo")
        assert r.owner == "octocat"

    def test_registry_create_invalid(self) -> None:
        from app.schemas.template_registry import RegistryCreate

        with pytest.raises(ValidationError):
            RegistryCreate(owner="", name="x")

    def test_registry_response(self) -> None:
        from app.schemas.template_registry import RegistryResponse

        now = datetime.now(UTC)
        resp = RegistryResponse(
            id=uuid.uuid4(),
            owner="o",
            name="n",
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        assert resp.owner == "o"

    def test_registry_sync_result_207(self) -> None:
        from app.schemas.template_registry import RegistrySyncItem, RegistrySyncResult

        r = RegistrySyncResult(
            registry_id=uuid.uuid4(),
            total=2,
            succeeded=1,
            failed=1,
            results=[RegistrySyncItem(pack_id="p1", status="success")],
        )
        assert r.total == 2

    def test_bulk_registry_sync_result(self) -> None:
        from app.schemas.common import BulkResult
        from app.schemas.template_registry import RegistrySyncItem

        br = BulkResult[RegistrySyncItem](
            total=1,
            succeeded=1,
            failed=0,
            results=[RegistrySyncItem(pack_id="p1", status="success")],
        )
        assert br.total == 1


class TestTemplatePackSchemas:
    def test_pack_create_valid(self) -> None:
        from app.schemas.template_pack import PackAssetCreate, PackCreate

        p = PackCreate(
            pack_id="docker-install",
            name="Docker Install",
            version="1.0.0",
            assets=[
                PackAssetCreate(
                    path="a.yml", content_base64=base64.b64encode(b"x").decode()
                )
            ],
        )
        assert p.pack_id == "docker-install"

    def test_pack_create_invalid(self) -> None:
        from app.schemas.template_pack import PackCreate

        with pytest.raises(ValidationError):
            PackCreate(pack_id="", name="n", version="1.0.0")

    def test_pack_local_create_request(self) -> None:
        from app.schemas.command import CommandCreate
        from app.schemas.script import ScriptCreate, ScriptStep
        from app.schemas.template_pack import (
            PackAssetCreateRequest,
            PackLocalCreateRequest,
            PackManifestRequest,
        )

        manifest = PackManifestRequest(pack_id="p1", name="P1", version="1.0.0")
        req = PackLocalCreateRequest(
            manifest=manifest,
            commands=[CommandCreate(name="c1", command="echo hi")],
            scripts=[
                ScriptCreate(
                    name="s1",
                    steps=[ScriptStep(label="l1", type="inline", command="echo hi")],
                )
            ],
            assets=[
                PackAssetCreateRequest(
                    path="a.txt", content_base64=base64.b64encode(b"hi").decode()
                )
            ],
        )
        assert req.manifest.pack_id == "p1"

    def test_bulk_pack_response_207(self) -> None:
        from app.schemas.template_pack import BulkPackResponse, BulkPackResult

        r = BulkPackResponse(
            total=2,
            succeeded=1,
            failed=1,
            results=[BulkPackResult(pack_id="p1", status="success")],
        )
        assert r.total == 2

    def test_pack_install_response(self) -> None:
        from app.schemas.template_pack import PackInstallResponse, PackInstallResult

        r = PackInstallResponse(
            pack_id=uuid.uuid4(),
            version="1.0.0",
            total=1,
            succeeded=1,
            failed=0,
            results=[
                PackInstallResult(entity_type="command", name="c1", status="success")
            ],
        )
        assert r.succeeded == 1

    def test_pack_stats_response(self) -> None:
        from app.schemas.template_pack import PackStatsResponse, StatsBucket

        s = PackStatsResponse(
            total=1,
            installed=1,
            not_installed=0,
            buckets=[StatsBucket(group="g", total=1, installed=1, not_installed=0)],
        )
        assert s.total == 1

    def test_pack_detail_with_assets(self) -> None:
        from app.schemas.template_pack import (
            PackAssetResponse,
            PackDetailWithAssetsResponse,
        )

        now = datetime.now(UTC)
        pid = uuid.uuid4()
        detail = PackDetailWithAssetsResponse(
            id=pid,
            registry_id=None,
            pack_id="p1",
            name="P1",
            description=None,
            version="1.0.0",
            author=None,
            tags=[],
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
            assets=[
                PackAssetResponse(
                    id=uuid.uuid4(),
                    pack_id=pid,
                    path="a.txt",
                    size=2,
                    sha="abc",
                    created_at=now,
                    updated_at=now,
                )
            ],
        )
        assert len(detail.assets) == 1


# ---------------------------------------------------------------------------
# Models: compose_project, template_*
# ---------------------------------------------------------------------------


class TestModels:
    def test_compose_project_model_creation(self) -> None:
        from app.models.compose_project import ComposeProjectModel

        now = datetime.now(UTC)
        m = ComposeProjectModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="proj",
            compose="version: '3'",
            env={"A": "b"},
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        assert m.project_name == "proj"
        assert m.compose == "version: '3'"
        assert m.env == {"A": "b"}

    def test_template_registry_model(self) -> None:
        from app.models.template_registry import TemplateRegistryModel

        now = datetime.now(UTC)
        m = TemplateRegistryModel(
            id=uuid.uuid4(),
            owner="octocat",
            name="repo",
            github_token_encrypted=None,
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        assert m.owner == "octocat"

    def test_template_pack_model(self) -> None:
        from app.models.template_pack import TemplatePackModel

        now = datetime.now(UTC)
        m = TemplatePackModel(
            id=uuid.uuid4(),
            registry_id=None,
            pack_id="p1",
            name="Pack",
            description=None,
            version="1.0.0",
            author=None,
            tags=["docker"],
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        assert m.pack_id == "p1"
        assert m.tags == ["docker"]

    def test_template_asset_model(self) -> None:
        from app.models.template_asset import TemplateAssetModel

        now = datetime.now(UTC)
        m = TemplateAssetModel(
            id=uuid.uuid4(),
            pack_id=uuid.uuid4(),
            path="assets/a.yml",
            content="hello",
            size=5,
            sha=hashlib.sha256(b"hello").hexdigest(),
            created_at=now,
            updated_at=now,
        )
        assert m.path == "assets/a.yml"

    def test_template_installation_model(self) -> None:
        from app.models.template_installation import TemplateInstallationModel

        now = datetime.now(UTC)
        m = TemplateInstallationModel(
            id=uuid.uuid4(),
            pack_id=uuid.uuid4(),
            entity_type="command",
            entity_id=uuid.uuid4(),
            created_at=now,
        )
        assert m.entity_type == "command"


# ---------------------------------------------------------------------------
# Compose service (mock reader/writer/runner)
# ---------------------------------------------------------------------------


class TestComposeServiceHelpers:
    def test_validate_project_name_ok(self) -> None:
        assert _validate_project_name("my-proj_1.2") == "my-proj_1.2"

    def test_validate_project_name_invalid(self) -> None:
        with pytest.raises(ValueError):
            _validate_project_name("bad/name")

        with pytest.raises(ValueError):
            _validate_project_name("")

        with pytest.raises(ValueError):
            _validate_project_name("a" * 101)

    def test_compose_file_path(self) -> None:
        p = _compose_file_path("my-proj")
        assert p.startswith("/tmp/nn-compose-")

    def test_env_prefix(self) -> None:
        assert _env_prefix(None) == ""
        assert _env_prefix({}) == ""
        pref = _env_prefix({"FOO": "bar", "A B": "c d"})
        assert "FOO" in pref

    def test_env_prefix_quoting(self) -> None:
        pref = _env_prefix({"K": "a b"})
        # shlex.quote should have been applied
        assert "a b" not in pref or "'" in pref or '"' in pref


@pytest.fixture
def mock_reader() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_writer() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_runner() -> AsyncMock:
    runner = AsyncMock()
    node = _mock_node()
    runner.get_target = AsyncMock(return_value=node)
    runner.build_command = MagicMock(
        return_value="docker compose -p proj -f /tmp/file.yml ps"
    )
    runner.execute = AsyncMock(return_value=("output", "", 0))
    return runner


class TestComposeService:
    async def test_create_project_success(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        dto = _make_compose_view()
        create_dto = ComposeCreateDTO(
            node_id=dto.node_id,
            project_name="proj1",
            compose="x",
            env=(),
            template_pack_id=None,
        )
        mock_writer.create_project.return_value = dto
        res = await svc.create_project(create_dto)
        assert res.project_name == "myproj"
        mock_writer.create_project.assert_awaited_once()

    async def test_create_invalid_name_raises(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        dto = ComposeCreateDTO(
            node_id=uuid.uuid4(), project_name="bad/name", compose="x"
        )
        with pytest.raises(ValueError):
            await svc.create_project(dto)

    async def test_list_projects(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        mock_reader.list_projects.return_value = [_make_compose_view(node_id=nid)]
        res = await svc.list_projects(nid, offset=0, limit=20)
        assert len(res) == 1

    async def test_list_all_projects_pagination(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        # first batch 100, second batch 1, third batch 0 to stop
        batch1 = [_make_compose_view(node_id=nid) for _ in range(100)]
        batch2 = [_make_compose_view(node_id=nid)]
        mock_reader.list_projects.side_effect = [batch1, batch2]
        res = await svc.list_all_projects(nid)
        assert len(res) == 101
        assert mock_reader.list_projects.call_count == 2

    async def test_count_and_stats(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        mock_reader.count_projects.return_value = 5
        mock_reader.stats.return_value = 5
        assert await svc.count_projects(nid) == 5
        assert await svc.stats(nid) == 5

    async def test_get_project_success(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        res = await svc.get_project(nid, "proj")
        assert res.project_name == "proj"

    async def test_get_project_not_found(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        mock_reader.get_project.return_value = None
        with pytest.raises(ComposeProjectNotFoundError):
            await svc.get_project(nid, "missing")

    async def test_update_project_success(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid)
        mock_writer.update_project.return_value = dto
        upd = ComposeUpdateDTO(compose="new")
        res = await svc.update_project(nid, "proj", upd)
        assert res is not None

    async def test_update_not_found(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        mock_writer.update_project.return_value = None
        with pytest.raises(ComposeProjectNotFoundError):
            await svc.update_project(nid, "proj", ComposeUpdateDTO(compose="x"))

    async def test_delete_success(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        mock_writer.delete_project.return_value = True
        await svc.delete_project(nid, "proj")
        mock_writer.delete_project.assert_awaited_once()

    async def test_delete_not_found(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        mock_writer.delete_project.return_value = False
        with pytest.raises(ComposeProjectNotFoundError):
            await svc.delete_project(nid, "proj")

    async def test_upsert(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        dto = _make_compose_view()
        create = ComposeCreateDTO(node_id=dto.node_id, project_name="p", compose="x")
        mock_writer.upsert_project.return_value = dto
        res = await svc.upsert_project(create)
        assert res is not None

    async def test_up_no_services_success(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(
            node_id=nid, project_name="proj", compose="x", env={"A": "b"}
        )
        mock_reader.get_project.return_value = dto
        # _run_compose will be called; mock runner to return output
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose up -d"
        mock_runner.execute.return_value = ("done", "", 0)
        res = await svc.up(nid, "proj", pull=False, build=False, services=None)
        assert res.total == 1
        assert res.succeeded == 1

    async def test_up_no_services_error(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj", compose="x")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose up -d"
        mock_runner.execute.return_value = ("", "error", 1)
        with patch(
            "app.application.services.compose_service.raise_for_docker_error",
            side_effect=Exception("docker error"),
        ):
            res = await svc.up(nid, "proj")
            assert res.failed == 1

    async def test_up_with_services(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj", compose="x")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose up -d web"
        mock_runner.execute.return_value = ("ok", "", 0)
        res = await svc.up(nid, "proj", services=["web", "db"])
        assert res.total == 2
        assert res.succeeded == 2

    async def test_up_with_pull_build(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj", compose="x")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = (
            "docker compose up -d --pull always --build web"
        )
        mock_runner.execute.return_value = ("ok", "", 0)
        res = await svc.up(nid, "proj", pull=True, build=True, services=["web"])
        assert res.total == 1

    async def test_down(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj", compose="x")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = (
            "docker compose down -v --remove-orphans --rmi all -t 30"
        )
        mock_runner.execute.return_value = ("removed", "", 0)
        out = await svc.down(
            nid, "proj", volumes=True, remove_orphans=True, timeout=30, images="all"
        )
        assert "removed" in out

    async def test_verb_bulk_no_services(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose start"
        mock_runner.execute.return_value = ("started", "", 0)
        res = await svc.verb_bulk(nid, "proj", "start", services=None)
        assert res.succeeded == 1

    async def test_verb_bulk_with_services(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose stop web"
        mock_runner.execute.return_value = ("stopped", "", 0)
        res = await svc.verb_bulk(nid, "proj", "stop", services=["web"], extra=" -t 10")
        assert res.total == 1

    async def test_ps_parses_json(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose ps --format json"
        # json per line
        out = (
            json.dumps({"ID": "abc", "Image": "nginx"})
            + "\n"
            + "invalid json\n"
            + json.dumps({"ID": "def"})
        )
        mock_runner.execute.return_value = (out, "", 0)
        res = await svc.ps(nid, "proj", all=False)
        assert len(res.containers) == 2

    async def test_ps_empty(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose ps"
        mock_runner.execute.return_value = ("", "", 0)
        res = await svc.ps(nid, "proj")
        assert res.containers == ()

    async def test_logs(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose logs"
        mock_runner.execute.return_value = ("log line", "", 0)
        out = await svc.logs(nid, "proj", tail=10, since="2024-01-01", services="web")
        assert "log line" in out

    async def test_config(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose config"
        mock_runner.execute.return_value = ("config yaml", "", 0)
        out = await svc.config(nid, "proj")
        assert "config" in out

    async def test_images_json(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose images"
        # first call succeeds with json
        out = json.dumps({"Repository": "nginx", "Tag": "latest"})
        mock_runner.execute.return_value = (out, "", 0)
        images, raw = await svc.images(nid, "proj")
        assert "nginx" in images

    async def test_images_fallback(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose images"
        # first call raises, second succeeds
        mock_runner.execute.side_effect = [
            Exception("fail"),
            ("nginx:latest\nredis:latest", "", 0),
        ]
        with patch(
            "app.application.services.compose_service.raise_for_docker_error",
            side_effect=lambda s, c: (
                (_ for _ in ()).throw(Exception("err")) if c != 0 else None
            ),
        ):
            pass
        svc._run_compose = AsyncMock(
            side_effect=[Exception("first"), "nginx:latest\nredis:latest"]
        )  # type: ignore[method-assign]
        images, raw = await svc.images(nid, "proj")
        assert "nginx:latest" in images

    async def test_top(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose top"
        mock_runner.execute.return_value = (
            "PID USER COMMAND\n1 root sleep 100\n2 root bash",
            "",
            0,
        )
        titles, procs, out = await svc.top(nid, "proj", service="web")
        assert "PID" in titles
        assert len(procs) == 2

    async def test_port(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose port web 80"
        mock_runner.execute.return_value = ("0.0.0.0:8080", "", 0)
        out = await svc.port(nid, "proj", service="web", private_port="80")
        assert "8080" in out

    async def test_version_try_success(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        node = _mock_node(nid)
        mock_runner.get_target.return_value = node
        mock_runner.build_command.return_value = "docker compose version --format json"
        mock_runner.execute.return_value = (json.dumps({"version": "v2.20.0"}), "", 0)
        ver, out = await svc.version(nid, "proj")
        assert "v2.20.0" in ver

    async def test_version_fallback(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        node = _mock_node(nid)
        mock_runner.get_target.return_value = node
        mock_runner.build_command.return_value = "docker compose version"
        # first path raises
        mock_runner.execute.side_effect = Exception("fail")
        svc._run_compose = AsyncMock(return_value="v2.20.0")  # type: ignore[method-assign]
        ver, out = await svc.version(nid, "proj")
        assert "v2.20.0" in ver

    async def test_exec(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose exec"
        mock_runner.execute.return_value = ("hello", "", 0)
        out, err, code = await svc.exec(
            nid, "proj", service="web", command="echo hi", timeout=30
        )
        assert out == "hello"
        assert code == 0

    async def test_run(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose run"
        mock_runner.execute.return_value = ("run output", "", 0)
        out = await svc.run(
            nid, "proj", service="web", command="echo hi", detached=False, timeout=60
        )
        assert "run output" in out

    async def test_run_detached(
        self, mock_reader: AsyncMock, mock_writer: AsyncMock, mock_runner: AsyncMock
    ) -> None:
        svc = ComposeService(reader=mock_reader, writer=mock_writer, runner=mock_runner)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_reader.get_project.return_value = dto
        mock_runner.get_target.return_value = _mock_node(nid)
        mock_runner.build_command.return_value = "docker compose run -d"
        mock_runner.execute.return_value = ("detached", "", 0)
        out = await svc.run(nid, "proj", service="web", detached=True)
        assert out == "detached"


# ---------------------------------------------------------------------------
# Persistence: compose gateway (mock session)
# ---------------------------------------------------------------------------


def _make_mock_sessionmaker() -> tuple[MagicMock, AsyncMock, AsyncMock]:
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.delete = AsyncMock()
    mock_session.get = AsyncMock()
    # for context manager of sessionmaker()
    mock_maker = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_session)
    cm.__aexit__ = AsyncMock(return_value=False)
    mock_maker.return_value = cm
    # for sessionmaker.begin()
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=mock_session)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_maker.begin.return_value = begin_cm
    return mock_maker, mock_session, cm


class TestComposePersistenceGateway:
    async def test_to_dto_mapping(self) -> None:
        from app.adapters.persistence.compose import _to_dto
        from app.models.compose_project import ComposeProjectModel

        now = datetime.now(UTC)
        model = ComposeProjectModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="p",
            compose="x",
            env={"A": "b"},
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        dto = _to_dto(model)
        assert dto.project_name == "p"
        assert dto.env == {"A": "b"}

    async def test_get_project_found(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        now = datetime.now(UTC)
        from app.models.compose_project import ComposeProjectModel

        model = ComposeProjectModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="p",
            compose="x",
            env=None,
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        mock_session.execute.return_value = mock_result
        nid = uuid.uuid4()
        res = await gateway.get_project(nid, "p")
        assert res is not None
        assert res.project_name == "p"

    async def test_get_project_not_found(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        res = await gateway.get_project(uuid.uuid4(), "missing")
        assert res is None

    async def test_list_projects(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        now = datetime.now(UTC)
        from app.models.compose_project import ComposeProjectModel

        model = ComposeProjectModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="p",
            compose="x",
            env=None,
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        mock_session.execute.return_value = mock_result
        res = await gateway.list_projects(uuid.uuid4(), offset=0, limit=20)
        assert len(res) == 1

    async def test_count_projects(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        mock_session.execute.return_value = mock_result
        cnt = await gateway.count_projects(uuid.uuid4())
        assert cnt == 5
        cnt2 = await gateway.stats(uuid.uuid4())
        assert cnt2 == 5

    async def test_create_project_success(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        nid = uuid.uuid4()
        data = ComposeCreateDTO(
            node_id=nid, project_name="p", compose="x", env=(), template_pack_id=None
        )
        # session.refresh will set attributes? We need to mock _to_dto to work.
        # The model after creation will be passed to _to_dto; we can patch _to_dto
        with patch("app.adapters.persistence.compose._to_dto") as mock_to:
            expected = _make_compose_view(node_id=nid, project_name="p")
            mock_to.return_value = expected
            res = await gateway.create_project(data)
            assert res.project_name == "p"

    async def test_create_project_duplicate(self) -> None:
        from sqlalchemy.exc import IntegrityError

        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        # make begin context raise IntegrityError
        mock_maker.begin.return_value.__aenter__ = AsyncMock(
            side_effect=IntegrityError("dup", params=None, orig=Exception("dup"))
        )
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        data = ComposeCreateDTO(node_id=uuid.uuid4(), project_name="p", compose="x")
        with pytest.raises(ComposeProjectAlreadyExistsError):
            await gateway.create_project(data)

    async def test_update_project_found(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        now = datetime.now(UTC)
        from app.models.compose_project import ComposeProjectModel

        model = ComposeProjectModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="p",
            compose="old",
            env=None,
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        mock_session.execute.return_value = mock_result
        with patch("app.adapters.persistence.compose._to_dto") as mock_to:
            mock_to.return_value = _make_compose_view(project_name="p", compose="new")
            upd = ComposeUpdateDTO(
                compose="new", has_env=False, has_template_pack_id=False
            )
            res = await gateway.update_project(uuid.uuid4(), "p", upd)
            assert res is not None

    async def test_update_project_not_found(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        upd = ComposeUpdateDTO(compose="new")
        res = await gateway.update_project(uuid.uuid4(), "p", upd)
        assert res is None

    async def test_delete_project_found(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        from app.models.compose_project import ComposeProjectModel

        now = datetime.now(UTC)
        model = ComposeProjectModel(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            project_name="p",
            compose="x",
            env=None,
            template_pack_id=None,
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = model
        mock_session.execute.return_value = mock_result
        res = await gateway.delete_project(uuid.uuid4(), "p")
        assert res is True

    async def test_delete_not_found(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        res = await gateway.delete_project(uuid.uuid4(), "missing")
        assert res is False

    async def test_upsert_create(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        # mock get_project to return None -> create
        gateway.get_project = AsyncMock(return_value=None)  # type: ignore[method-assign]
        gateway.create_project = AsyncMock(
            return_value=_make_compose_view(project_name="p")
        )  # type: ignore[method-assign]
        data = ComposeCreateDTO(node_id=uuid.uuid4(), project_name="p", compose="x")
        res = await gateway.upsert_project(data)
        assert res.project_name == "p"

    async def test_upsert_update(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        existing = _make_compose_view(project_name="p")
        gateway.get_project = AsyncMock(return_value=existing)  # type: ignore[method-assign]
        gateway.update_project = AsyncMock(return_value=existing)  # type: ignore[method-assign]
        data = ComposeCreateDTO(
            node_id=existing.node_id, project_name="p", compose="new"
        )
        res = await gateway.upsert_project(data)
        assert res is not None

    async def test_upsert_raced_delete(self) -> None:
        from app.adapters.persistence.compose import SqlAlchemyComposeGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyComposeGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        existing = _make_compose_view(project_name="p")
        gateway.get_project = AsyncMock(return_value=existing)  # type: ignore[method-assign]
        gateway.update_project = AsyncMock(return_value=None)  # type: ignore[method-assign]
        gateway.create_project = AsyncMock(return_value=existing)  # type: ignore[method-assign]
        data = ComposeCreateDTO(
            node_id=existing.node_id, project_name="p", compose="new"
        )
        res = await gateway.upsert_project(data)
        assert res is not None


# ---------------------------------------------------------------------------
# API v2 compose (test client for POST /api/v2/nodes/{id}/docker/compose/projects)
# ---------------------------------------------------------------------------


def _create_compose_app(mock_service: AsyncMock) -> FastAPI:
    from app.api.v2.compose import router as compose_router

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_compose_service(self) -> ComposeService:
            return as_typed_mock(ComposeService, mock_service)

    app.include_router(compose_router, prefix="/api/v2")
    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


class TestComposeApiV2:
    async def test_create_project_success(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_service.create_project.return_value = dto
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects",
                    json={"project_name": "proj", "compose": "version: '3'"},
                )
        assert resp.status_code == 201
        assert resp.json()["project_name"] == "proj"

    async def test_create_project_conflict(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        mock_service.create_project.side_effect = ComposeProjectAlreadyExistsError(
            "exists"
        )
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects",
                    json={"project_name": "proj", "compose": "x"},
                )
        assert resp.status_code == 409

    async def test_create_invalid_name_422(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects",
                    json={"project_name": "bad/name", "compose": "x"},
                )
        assert resp.status_code == 422

    async def test_list_projects_cursor(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        dto1 = _make_compose_view(node_id=nid, project_name="p1")
        dto2 = _make_compose_view(node_id=nid, project_name="p2")
        mock_service.list_all_projects.return_value = [dto1, dto2]
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects?limit=1"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    async def test_list_invalid_cursor(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        mock_service.list_all_projects.return_value = []
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects?cursor=invalid"
                )
        assert resp.status_code == 422

    async def test_get_project_success(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj")
        mock_service.get_project.return_value = dto
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj"
                )
        assert resp.status_code == 200

    async def test_get_project_not_found(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        mock_service.get_project.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/missing"
                )
        assert resp.status_code == 404

    async def test_update_project(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        dto = _make_compose_view(node_id=nid, project_name="proj", compose="new")
        mock_service.update_project.return_value = dto
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.patch(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj",
                    json={"compose": "new"},
                )
        assert resp.status_code == 200

    async def test_delete_project(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        mock_service.delete_project.return_value = None
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.delete(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj"
                )
        assert resp.status_code == 204

    async def test_compose_up_207(self) -> None:
        from app.application.dto.compose import (
            ComposeBulkResultDTO,
            ComposeServiceResultDTO,
        )

        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        bulk = ComposeBulkResultDTO(
            total=2,
            succeeded=1,
            failed=1,
            results=(
                ComposeServiceResultDTO(service="web", status="success", output="ok"),
                ComposeServiceResultDTO(service="db", status="error", error="fail"),
            ),
        )
        mock_service.up.return_value = bulk
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/ups",
                    json={"pull": False, "build": False},
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["total"] == 2
        assert data["failed"] == 1

    async def test_compose_down_success(self) -> None:
        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        mock_service.down.return_value = "removed"
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/downs",
                    json={"volumes": True},
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "removed"

    async def test_compose_ps_success(self) -> None:
        from app.application.dto.compose import ComposePsDTO

        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        mock_service.ps.return_value = ComposePsDTO(
            output="ps", containers=({"ID": "abc"},)
        )
        app = _create_compose_app(mock_service)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/ps"
                )
        assert resp.status_code == 200

    async def test_compose_helpers(self) -> None:
        from app.api.v2.compose import (
            _decode_offset,
            _encode_offset,
            _paginate_offset,
            _validate_project_name,
        )

        assert _validate_project_name("valid-1") == "valid-1"
        with pytest.raises(Exception):
            _validate_project_name("bad/name")
        cur = _encode_offset(5)
        assert _decode_offset(cur) == 5
        items = list(range(10))
        sliced, nxt, has_more = _paginate_offset(items, None, 3)
        assert len(sliced) == 3
        assert has_more is True
        with pytest.raises(Exception):
            _paginate_offset(items, "invalid", 3)

    async def test_compose_bulk_to_response(self) -> None:
        from app.api.v2.compose import _bulk_to_response
        from app.application.dto.compose import (
            ComposeBulkResultDTO,
            ComposeServiceResultDTO,
        )

        bulk = ComposeBulkResultDTO(
            total=1,
            succeeded=1,
            failed=0,
            results=(
                ComposeServiceResultDTO(service="s", status="success", output="ok"),
            ),
        )
        res = _bulk_to_response(bulk)
        assert res.total == 1

    async def test_compose_to_response(self) -> None:
        from app.api.v2.compose import _to_response

        dto = _make_compose_view()
        resp = _to_response(dto)
        assert resp.project_name == dto.project_name


# ---------------------------------------------------------------------------
# API v2 templates (registries/packs install with on_conflict)
# ---------------------------------------------------------------------------


def _create_templates_app(
    registry_service: AsyncMock | MagicMock, pack_service: AsyncMock | MagicMock
) -> FastAPI:
    from app.api.v2.templates import router as templates_router
    from app.application.services.template_pack_service import TemplatePackService
    from app.application.services.template_registry_service import (
        TemplateRegistryService,
    )

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_registry_service(self) -> TemplateRegistryService:
            return as_typed_mock(TemplateRegistryService, registry_service)

        @provide(scope=Scope.REQUEST)
        def get_pack_service(self) -> TemplatePackService:
            return as_typed_mock(TemplatePackService, pack_service)

    app.include_router(templates_router, prefix="/api/v2")
    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


class TestTemplatesApiV2:
    async def test_create_registry_success(self) -> None:
        from app.application.dto.template_registry import RegistryViewDTO

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        now = datetime.now(UTC)
        view = RegistryViewDTO(
            id=uuid.uuid4(),
            owner="octocat",
            name="repo",
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        mock_reg.create_registry.return_value = view
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    "/api/v2/templates/registries",
                    json={"owner": "octocat", "name": "repo"},
                )
        assert resp.status_code == 201

    async def test_create_registry_conflict(self) -> None:
        from app.application.services.template_registry_service import (
            RegistryConflictError,
        )

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        mock_reg.create_registry.side_effect = RegistryConflictError("exists")
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    "/api/v2/templates/registries", json={"owner": "o", "name": "n"}
                )
        assert resp.status_code == 409

    async def test_list_registries_cursor(self) -> None:
        from app.application.dto.template_registry import (
            RegistryPageDTO,
            RegistryViewDTO,
        )

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        now = datetime.now(UTC)
        v1 = RegistryViewDTO(
            id=uuid.uuid4(),
            owner="o",
            name="r1",
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        mock_reg.list_registries.return_value = RegistryPageDTO(items=(v1,), total=2)
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get("/api/v2/templates/registries?limit=1")
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True

    async def test_list_registries_invalid_cursor(self) -> None:
        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get("/api/v2/templates/registries?cursor=bad")
        assert resp.status_code == 422

    async def test_get_registry(self) -> None:
        from app.application.dto.template_registry import RegistryViewDTO

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        now = datetime.now(UTC)
        view = RegistryViewDTO(
            id=uuid.uuid4(),
            owner="o",
            name="r",
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        mock_reg.get_registry.return_value = view
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.get(f"/api/v2/templates/registries/{view.id}")
        assert resp.status_code == 200

    async def test_sync_registry_207(self) -> None:
        from app.application.dto.template_registry import (
            RegistrySyncItemDTO,
            RegistrySyncResultDTO,
        )

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        rid = uuid.uuid4()
        result = RegistrySyncResultDTO(
            registry_id=rid,
            total=2,
            succeeded=1,
            failed=1,
            results=(
                RegistrySyncItemDTO(pack_id="p1", status="success"),
                RegistrySyncItemDTO(pack_id="p2", status="error", error="fail"),
            ),
        )
        mock_reg.sync_registry.return_value = result
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(f"/api/v2/templates/registries/{rid}/syncs")
        assert resp.status_code == 207

    async def test_create_pack(self) -> None:
        from app.application.dto.template_pack import (
            PackAssetDTO,
            PackDetailDTO,
            PackViewDTO,
        )

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        now = datetime.now(UTC)
        pid = uuid.uuid4()
        view = PackViewDTO(
            id=pid,
            registry_id=None,
            pack_id="p1",
            name="P1",
            description=None,
            version="1.0.0",
            author=None,
            tags=(),
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        asset = PackAssetDTO(
            id=uuid.uuid4(),
            pack_id=pid,
            path="a.txt",
            size=2,
            sha="abc",
            created_at=now,
            updated_at=now,
        )
        detail = PackDetailDTO(pack=view, assets=(asset,), commands=(), scripts=())
        mock_pack.create_pack.return_value = detail
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    "/api/v2/templates/packs",
                    json={
                        "manifest": {"pack_id": "p1", "name": "P1", "version": "1.0.0"},
                        "commands": [],
                        "scripts": [],
                    },
                )
        assert resp.status_code == 201

    async def test_create_pack_conflict(self) -> None:
        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        mock_pack.create_pack.side_effect = DomainError(
            "Pack p1 already exists for registry"
        )
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    "/api/v2/templates/packs",
                    json={
                        "manifest": {"pack_id": "p1", "name": "P1", "version": "1.0.0"}
                    },
                )
        assert resp.status_code == 409

    async def test_install_pack_on_conflict_rename(self) -> None:
        from app.application.dto.template_pack import (
            PackInstallItemDTO,
            PackInstallResultDTO,
        )

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        pid = uuid.uuid4()
        result = PackInstallResultDTO(
            pack_id=pid,
            version="1.0.0",
            total=1,
            succeeded=1,
            failed=0,
            results=(
                PackInstallItemDTO(
                    entity_type="command",
                    entity_id=uuid.uuid4(),
                    name="c1",
                    status="success",
                ),
            ),
        )
        mock_pack.install_pack.return_value = result
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/templates/packs/{pid}/installations?on_conflict=rename"
                )
        assert resp.status_code == 201
        mock_pack.install_pack.assert_awaited_once_with(pid, on_conflict="rename")

    async def test_install_pack_conflict_409(self) -> None:
        from app.application.services.template_pack_service import PackConflictError

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        pid = uuid.uuid4()
        mock_pack.install_pack.side_effect = PackConflictError("conflict")
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/templates/packs/{pid}/installations?on_conflict=fail"
                )
        assert resp.status_code == 409

    async def test_install_207_partial(self) -> None:
        from app.application.dto.template_pack import (
            PackInstallItemDTO,
            PackInstallResultDTO,
        )

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        pid = uuid.uuid4()
        result = PackInstallResultDTO(
            pack_id=pid,
            version="1.0.0",
            total=2,
            succeeded=1,
            failed=1,
            results=(
                PackInstallItemDTO(
                    entity_type="command",
                    entity_id=uuid.uuid4(),
                    name="c1",
                    status="success",
                ),
                PackInstallItemDTO(
                    entity_type="command",
                    entity_id=None,
                    name="c2",
                    status="error",
                    error="fail",
                ),
            ),
        )
        mock_pack.install_pack.return_value = result
        app = _create_templates_app(mock_reg, mock_pack)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(f"/api/v2/templates/packs/{pid}/installations")
        assert resp.status_code == 207

    async def test_templates_helpers(self) -> None:
        from app.api.v2.templates import (
            _decode_offset,
            _encode_offset,
            _pack_detail_response,
            _pack_response,
            _registry_response,
        )
        from app.application.dto.template_pack import (
            PackAssetDTO,
            PackDetailDTO,
            PackViewDTO,
        )
        from app.application.dto.template_registry import RegistryViewDTO

        now = datetime.now(UTC)
        rv = RegistryViewDTO(
            id=uuid.uuid4(),
            owner="o",
            name="n",
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        assert _registry_response(rv).owner == "o"
        pv = PackViewDTO(
            id=uuid.uuid4(),
            registry_id=None,
            pack_id="p1",
            name="N",
            description=None,
            version="1.0.0",
            author=None,
            tags=(),
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        assert _pack_response(pv).pack_id == "p1"
        asset = PackAssetDTO(
            id=uuid.uuid4(),
            pack_id=pv.id,
            path="a",
            size=1,
            sha="s",
            created_at=now,
            updated_at=now,
        )
        detail = PackDetailDTO(pack=pv, assets=(asset,), commands=(), scripts=())
        assert len(_pack_detail_response(detail).assets) == 1
        cur = _encode_offset(10)
        assert _decode_offset(cur) == 10
        with pytest.raises(ValueError):
            _decode_offset("bad")


# ---------------------------------------------------------------------------
# Template pack/registry services (in-memory)
# ---------------------------------------------------------------------------


class TestTemplatePackService:
    async def test_create_and_get(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(
            pack_id="p1", name="P1", version="1.0.0", tags=("t1",)
        )
        content = base64.b64encode(b"hello world").decode()
        asset = PackAssetCreateDTO(path="a.txt", content_base64=content)
        data = PackCreateDTO(
            manifest=manifest, commands=(), scripts=(), assets=(asset,)
        )
        detail = await svc.create_pack(data)
        assert detail.pack.pack_id == "p1"
        fetched = await svc.get_pack_detail(detail.pack.id)
        assert fetched.pack.name == "P1"
        view = await svc.get_pack_view(detail.pack.id)
        assert view.version == "1.0.0"
        tar = await svc.get_assets_tar(detail.pack.id)
        assert len(tar) > 0
        # verify tar contains file
        buf = io.BytesIO(tar)
        with tarfile.open(fileobj=buf, mode="r") as tf:
            names = tf.getnames()
            assert "a.txt" in names
        tar2 = await svc.stream_assets_tar(detail.pack.id)
        assert tar == tar2

    async def test_create_duplicate_raises(self) -> None:
        from app.application.services.template_pack_service import (
            _INSTALLATIONS,
            _PACKS,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="dup", name="P", version="1.0.0")
        data = PackCreateDTO(manifest=manifest)
        await svc.create_pack(data)
        with pytest.raises(DomainError):
            await svc.create_pack(data)

    async def test_create_invalid_base64(self) -> None:
        from app.application.services.template_pack_service import (
            _INSTALLATIONS,
            _PACKS,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="p2", name="P2", version="1.0.0")
        bad = PackAssetCreateDTO(path="a", content_base64="!!!notbase64")
        data = PackCreateDTO(manifest=manifest, assets=(bad,))
        with pytest.raises(DomainError):
            await svc.create_pack(data)

    async def test_install_and_uninstall(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="p3", name="P3", version="1.0.0")
        data = PackCreateDTO(
            manifest=manifest, commands=({"name": "c1"},), scripts=({"name": "s1"},)
        )
        detail = await svc.create_pack(data)
        res = await svc.install_pack(detail.pack.id, on_conflict="fail")
        assert res.succeeded == 2
        # already installed -> conflict
        with pytest.raises(Exception):
            await svc.install_pack(detail.pack.id, on_conflict="fail")
        await svc.uninstall_pack(detail.pack.id)
        # reinstall should succeed after uninstall
        res2 = await svc.install_pack(detail.pack.id, on_conflict="fail")
        assert res2.succeeded == 2

    async def test_install_on_conflict_rename(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        # pre-populate global name to force conflict
        _COMMAND_NAMES.add("c1")
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="p4", name="P4", version="1.0.0")
        data = PackCreateDTO(manifest=manifest, commands=({"name": "c1"},))
        detail = await svc.create_pack(data)
        # fail should raise
        with pytest.raises(Exception):
            await svc.install_pack(detail.pack.id, on_conflict="fail")
        # rename should succeed with new name
        res = await svc.install_pack(detail.pack.id, on_conflict="rename")
        assert res.succeeded == 1
        assert res.results[0].name == "c1_1"

    async def test_install_with_fail_entity(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="p5", name="P5", version="1.0.0")
        data = PackCreateDTO(manifest=manifest, commands=({"name": "will-fail"},))
        detail = await svc.create_pack(data)
        res = await svc.install_pack(detail.pack.id, on_conflict="fail")
        assert res.failed == 1
        assert res.succeeded == 0

    async def test_list_and_stats(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(
            pack_id="p6", name="P6", version="1.0.0", tags=("docker",)
        )
        await svc.create_pack(
            PackCreateDTO(manifest=manifest, commands=({"name": "c0"},))
        )
        manifest2 = PackManifestDTO(pack_id="p7", name="Other", version="2.0.0")
        detail2 = await svc.create_pack(
            PackCreateDTO(manifest=manifest2, commands=({"name": "c1"},))
        )
        await svc.install_pack(detail2.pack.id)
        page = await svc.list_packs(PackListQueryDTO(offset=0, limit=10, tag="docker"))
        assert page.total == 1
        page2 = await svc.list_packs(
            PackListQueryDTO(offset=0, limit=10, search="other")
        )
        assert page2.total == 1
        page3 = await svc.list_packs(
            PackListQueryDTO(offset=0, limit=10, installed=True)
        )
        assert page3.total == 1
        stats = await svc.get_stats(group_by="tag")
        assert stats.total == 2
        stats2 = await svc.get_stats(group_by="registry_id")
        assert stats2.total == 2
        stats3 = await svc.get_stats(group_by="installed")
        assert len(stats3.buckets) == 2
        stats4 = await svc.get_stats(group_by="version")
        assert any(b.group == "1.0.0" for b in stats4.buckets)
        stats5 = await svc.get_stats(group_by="custom")
        assert stats5.total == 2

    async def test_update_pack(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="p8", name="P8", version="1.0.0")
        detail = await svc.create_pack(
            PackCreateDTO(manifest=manifest, commands=({"name": "c1"},))
        )
        await svc.install_pack(detail.pack.id)
        res = await svc.update_pack(detail.pack.id, on_conflict="fail")
        assert res.succeeded == 1

    async def test_list_installations(self) -> None:
        from app.application.services.template_pack_service import (
            _ASSET_RAW,
            _COMMAND_NAMES,
            _INSTALLATION_NAMES,
            _INSTALLATIONS,
            _PACKS,
            _SCRIPT_NAMES,
        )

        _PACKS.clear()
        _INSTALLATIONS.clear()
        _ASSET_RAW.clear()
        _COMMAND_NAMES.clear()
        _SCRIPT_NAMES.clear()
        _INSTALLATION_NAMES.clear()
        from app.application.services.template_pack_service import TemplatePackService

        svc = TemplatePackService()
        manifest = PackManifestDTO(pack_id="p9", name="P9", version="1.0.0")
        detail = await svc.create_pack(
            PackCreateDTO(manifest=manifest, commands=({"name": "c1"},))
        )
        await svc.install_pack(detail.pack.id)
        page = await svc.list_installations(detail.pack.id, offset=0, limit=10)
        assert page.total == 1
        with pytest.raises(Exception):
            await svc.list_installations(uuid.uuid4(), offset=0, limit=10)
        with pytest.raises(Exception):
            await svc.get_pack_detail(uuid.uuid4())


class TestTemplateRegistryService:
    async def test_create_list_get_delete_sync(self) -> None:
        from app.application.services.template_registry_service import _REGISTRIES

        _REGISTRIES.clear()
        from app.application.services.template_registry_service import (
            TemplateRegistryService,
        )

        svc = TemplateRegistryService()
        dto = RegistryCreateDTO(owner="octocat", name="repo", default_branch="main")
        view = await svc.create_registry(dto)
        assert view.owner == "octocat"
        # duplicate should raise
        with pytest.raises(Exception):
            await svc.create_registry(dto)
        page = await svc.list_registries(offset=0, limit=10)
        assert page.total == 1
        fetched = await svc.get_registry(view.id)
        assert fetched.name == "repo"
        with pytest.raises(Exception):
            await svc.get_registry(uuid.uuid4())
        sync = await svc.sync_registry(view.id)
        assert sync.registry_id == view.id
        with pytest.raises(Exception):
            await svc.sync_registry(uuid.uuid4())
        await svc.delete_registry(view.id)
        with pytest.raises(Exception):
            await svc.delete_registry(view.id)
        with pytest.raises(Exception):
            await svc.get_registry(view.id)


# ---------------------------------------------------------------------------
# Docker container service new methods (kill/update/archive/port/wait)
# ---------------------------------------------------------------------------


class TestContainerServiceNewMethods:
    async def test_kill_success(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(
            return_value="docker kill --signal SIGTERM abc123"
        )
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        await svc.kill_container(uuid.uuid4(), "abc123", signal="SIGTERM")
        runner.execute.assert_awaited_once()

    async def test_update_success(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(
            return_value="docker update --memory 512m abc123"
        )
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        await svc.update_container(uuid.uuid4(), "abc123", memory="512m")
        runner.execute.assert_awaited_once()

    async def test_update_no_fields_raises(self) -> None:
        runner = AsyncMock()
        svc = DockerContainerService(runner=runner)
        with pytest.raises(DockerValidationError):
            await svc.update_container(uuid.uuid4(), "abc123")

    async def test_update_with_restart_policy(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(
            return_value="docker update --restart always abc123"
        )
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        await svc.update_container(uuid.uuid4(), "abc123", restart_policy="always")
        assert "always" in runner.build_command.call_args[0][1]

    async def test_get_archive(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker cp abc123:/path -")
        runner.execute = AsyncMock(return_value=("file content", "", 0))
        svc = DockerContainerService(runner=runner)
        out = await svc.get_archive(uuid.uuid4(), "abc123", "/path")
        assert out == "file content"

    async def test_put_archive(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker cp - abc123:/path")
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        await svc.put_archive(uuid.uuid4(), "abc123", "/path", "data")
        runner.execute.assert_awaited_once()

    async def test_get_port(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker port abc123 80")
        runner.execute = AsyncMock(return_value=("0.0.0.0:8080", "", 0))
        svc = DockerContainerService(runner=runner)
        out = await svc.get_port(uuid.uuid4(), "abc123", private_port="80")
        assert "8080" in out

    async def test_get_port_no_private(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker port abc123")
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        out = await svc.get_port(uuid.uuid4(), "abc123")
        assert out == ""

    async def test_wait_success(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker wait abc123")
        runner.execute = AsyncMock(return_value=("0", "", 0))
        svc = DockerContainerService(runner=runner)
        code = await svc.wait_container(uuid.uuid4(), "abc123")
        assert code == 0

    async def test_wait_non_int(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker wait abc123")
        runner.execute = AsyncMock(return_value=("not-an-int", "", 0))
        svc = DockerContainerService(runner=runner)
        code = await svc.wait_container(uuid.uuid4(), "abc123")
        assert code == 0

    async def test_pause_unpause_rename_top(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker pause abc123")
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        await svc.pause_container(uuid.uuid4(), "abc123")
        runner.build_command = MagicMock(return_value="docker unpause abc123")
        await svc.unpause_container(uuid.uuid4(), "abc123")
        runner.build_command = MagicMock(return_value="docker rename abc123 newname")
        await svc.rename_container(
            ContainerRenameRequestDTO(
                node_id=uuid.uuid4(), container_id="abc123", new_name="newname"
            )
        )
        # top
        runner.build_command = MagicMock(return_value="docker top abc123")
        runner.execute = AsyncMock(return_value=("PID USER\n1 root\n2 root", "", 0))
        res = await svc.top_container(uuid.uuid4(), "abc123")
        assert len(res.titles) == 2

    async def test_top_not_found(self) -> None:
        runner = AsyncMock()
        node = _mock_node()
        runner.get_target = AsyncMock(return_value=node)
        runner.build_command = MagicMock(return_value="docker top abc123")
        runner.execute = AsyncMock(return_value=("", "", 0))
        svc = DockerContainerService(runner=runner)
        with pytest.raises(Exception):
            await svc.top_container(uuid.uuid4(), "abc123")


# ---------------------------------------------------------------------------
# API v2 docker new vert bulk endpoints
# ---------------------------------------------------------------------------


def _create_docker_app(mock_service: AsyncMock) -> FastAPI:
    from app.api.v2.docker import router as docker_router
    from app.application.services.docker.container_service import DockerContainerService
    from app.application.services.docker.image_service import DockerImageService
    from app.application.services.docker.resource_service import DockerResourceService
    from app.application.services.docker.system_service import DockerSystemService

    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_container_service(self) -> DockerContainerService:
            return as_typed_mock(DockerContainerService, mock_service)

        @provide(scope=Scope.REQUEST)
        def get_image_service(self) -> DockerImageService:
            return as_typed_mock(DockerImageService, mock_service)

        @provide(scope=Scope.REQUEST)
        def get_resource_service(self) -> DockerResourceService:
            return as_typed_mock(DockerResourceService, mock_service)

        @provide(scope=Scope.REQUEST)
        def get_system_service(self) -> DockerSystemService:
            return as_typed_mock(DockerSystemService, mock_service)

    app.include_router(docker_router, prefix="/api/v2")
    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


class TestDockerBulkApiV2:
    async def test_bulk_starts_success(self) -> None:
        mock = AsyncMock()
        mock.start_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/starts",
                    json={"container_ids": ["abc123", "def456"]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2

    async def test_bulk_starts_207(self) -> None:
        mock = AsyncMock()

        async def _fail(node_id: UUID, cid: str) -> None:
            if cid == "bad":
                raise DockerValidationError("bad id")
            return None

        mock.start_container.side_effect = _fail
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/starts",
                    json={"container_ids": ["abc123", "bad"]},
                )
        assert resp.status_code == 207
        assert resp.json()["failed"] == 1

    async def test_bulk_stops(self) -> None:
        mock = AsyncMock()
        mock.stop_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/stops?timeout=10",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_restarts(self) -> None:
        mock = AsyncMock()
        mock.restart_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/restarts",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_removals(self) -> None:
        mock = AsyncMock()
        mock.remove_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/removals",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_pauses(self) -> None:
        mock = AsyncMock()
        mock.pause_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/pauses",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_unpauses(self) -> None:
        mock = AsyncMock()
        mock.unpause_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/unpauses",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_kills(self) -> None:
        mock = AsyncMock()
        mock.kill_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/kills",
                    json={"container_ids": ["abc123"], "signal": "SIGKILL"},
                )
        assert resp.status_code == 200

    async def test_bulk_updates(self) -> None:
        mock = AsyncMock()
        mock.update_container = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/updates",
                    json={"container_ids": ["abc123"], "memory": "512m"},
                )
        assert resp.status_code == 200

    async def test_bulk_executions(self) -> None:
        from app.application.dto.docker import DockerExecResultDTO

        mock = AsyncMock()
        mock.exec_command = AsyncMock(
            return_value=DockerExecResultDTO(stdout="out", stderr="", exit_code=0)
        )
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/executions",
                    json={"container_ids": ["abc123"], "command": "echo hi"},
                )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_bulk_inspections(self) -> None:
        from app.application.dto.docker import (
            DockerContainerConfigDTO,
            DockerContainerInspectDTO,
            DockerContainerStateDTO,
        )

        mock = AsyncMock()
        mock.get_container = AsyncMock(
            return_value=DockerContainerInspectDTO(
                id="abc123",
                name="/test",
                state=DockerContainerStateDTO(
                    status="running", running=True, exit_code=0
                ),
                config=DockerContainerConfigDTO(image="nginx"),
                network_settings=(),
            )
        )
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/inspections",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_logs(self) -> None:
        mock = AsyncMock()
        mock.get_logs = AsyncMock(return_value="log line")
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/logs",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_bulk_stats(self) -> None:
        from app.application.dto.docker import DockerStatsDTO

        mock = AsyncMock()
        mock.get_stats = AsyncMock(
            return_value=DockerStatsDTO(
                container_id="abc123",
                name="web",
                cpu_percent="1%",
                mem_usage="10M",
                mem_percent="5%",
                net_io="0",
                block_io="0",
            )
        )
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/stats",
                    json={"container_ids": ["abc123"]},
                )
        assert resp.status_code == 200

    async def test_single_kill_update_archive_port_wait(self) -> None:
        mock = AsyncMock()
        mock.kill_container = AsyncMock(return_value=None)
        mock.update_container = AsyncMock(return_value=None)
        mock.get_archive = AsyncMock(return_value="data")
        mock.put_archive = AsyncMock(return_value=None)
        mock.get_port = AsyncMock(return_value="0.0.0.0:8080")
        mock.wait_container = AsyncMock(return_value=0)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        cid = "abc123def456"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/{cid}/kill",
                    json={"signal": "SIGTERM"},
                )
                assert resp.status_code == 200
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/{cid}/update",
                    json={"memory": "512m"},
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/containers/{cid}/archive?path=/tmp/file"
                )
                assert resp.status_code == 200
                resp = await client.put(
                    f"/api/v2/nodes/{nid}/docker/containers/{cid}/archive?path=/tmp/file&data=hello"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/containers/{cid}/port?private_port=80"
                )
                assert resp.status_code == 200
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/containers/{cid}/wait"
                )
                assert resp.status_code == 200

    async def test_docker_helpers(self) -> None:
        from app.api.v2.docker import _decode_offset, _encode_offset, _paginate_offset

        cur = _encode_offset(3)
        assert _decode_offset(cur) == 3
        items = [1, 2, 3, 4]
        sliced, nxt, has_more = _paginate_offset(items, None, 2)
        assert len(sliced) == 2
        assert has_more is True
        with pytest.raises(Exception):
            _paginate_offset(items, "bad", 2)

    async def test_image_bulk_pulls(self) -> None:
        from app.application.dto.docker import DockerPullResultDTO

        mock = AsyncMock()
        mock.pull_image = AsyncMock(
            return_value=DockerPullResultDTO(
                image="nginx", output="pulled", success=True
            )
        )
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/images/pulls",
                    json={"images": ["nginx", "redis"]},
                )
        assert resp.status_code == 200

    async def test_image_bulk_removals(self) -> None:
        mock = AsyncMock()
        mock.remove_image = AsyncMock(return_value=None)
        app = _create_docker_app(mock)
        nid = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "test-master"},
        ) as client:
            with patch(
                "app.api.deps.get_settings", return_value=_mock_settings("test-master")
            ):
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/images/removals",
                    json={"image_ids": ["abc123"]},
                )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Additional persistence: template_asset / template_pack gateways
# ---------------------------------------------------------------------------


class TestTemplatePersistenceGateways:
    async def test_template_asset_write_and_list(self) -> None:
        from app.adapters.persistence.template_asset import (
            SqlAlchemyTemplateAssetGateway,
        )

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyTemplateAssetGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        pid = uuid.uuid4()
        asset = PackAssetCreateDTO(
            path="a.txt", content_base64=base64.b64encode(b"hello").decode()
        )
        # patch uuid and datetime for determinism
        res = await gateway.write_assets(pid, (asset,))
        assert len(res) == 1
        assert res[0].size == 5
        # list
        now = datetime.now(UTC)
        from app.models.template_asset import TemplateAssetModel

        model = TemplateAssetModel(
            id=uuid.uuid4(),
            pack_id=pid,
            path="a.txt",
            content="hello",
            size=5,
            sha=hashlib.sha256(b"hello").hexdigest(),
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [model]
        mock_session.execute.return_value = mock_result
        # need to override maker for list call to return session with execute
        # reuse same mock_maker
        listed = await gateway.list_assets(pid)
        assert len(listed) == 1
        # tar
        tar_bytes = await gateway.get_assets_tar(pid)
        assert len(tar_bytes) > 0

    async def test_template_asset_invalid_base64(self) -> None:
        from app.adapters.persistence.template_asset import (
            SqlAlchemyTemplateAssetGateway,
        )

        mock_maker, _, _ = _make_mock_sessionmaker()
        gateway = SqlAlchemyTemplateAssetGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        pid = uuid.uuid4()
        bad = PackAssetCreateDTO(path="a", content_base64="!!bad")
        with pytest.raises(DomainError):
            await gateway.write_assets(pid, (bad,))

    async def test_template_pack_gateway_create(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        # mock asset gateway write_assets to avoid DB
        gateway._asset_gateway.write_assets = AsyncMock(return_value=())  # type: ignore[method-assign]
        data = PackCreateDTO(
            manifest=PackManifestDTO(pack_id="p1", name="N", version="1.0.0"), assets=()
        )
        detail = await gateway.create_pack(data)
        assert detail.pack.pack_id == "p1"

    async def test_template_pack_gateway_duplicate(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        mock_result = MagicMock()
        # simulate existing pack found
        mock_result.scalar_one_or_none.return_value = MagicMock()
        mock_session.execute.return_value = mock_result
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        data = PackCreateDTO(
            manifest=PackManifestDTO(pack_id="p1", name="N", version="1.0.0")
        )
        with pytest.raises(DomainError):
            await gateway.create_pack(data)

    async def test_template_pack_gateway_get_pack(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.models.template_pack import TemplatePackModel

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        now = datetime.now(UTC)
        pid = uuid.uuid4()
        model = TemplatePackModel(
            id=pid,
            registry_id=None,
            pack_id="p1",
            name="N",
            description=None,
            version="1.0.0",
            author=None,
            tags=[],
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        mock_session.get = AsyncMock(return_value=model)
        # list_assets will be called inside get_pack; mock it
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        gateway._asset_gateway.list_assets = AsyncMock(return_value=())  # type: ignore[method-assign]
        detail = await gateway.get_pack(pid)
        assert detail is not None
        assert detail.pack.pack_id == "p1"
        mock_session.get.return_value = None
        none = await gateway.get_pack(uuid.uuid4())
        assert none is None

    async def test_template_pack_gateway_list_packs(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.models.template_pack import TemplatePackModel

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        now = datetime.now(UTC)
        m1 = TemplatePackModel(
            id=uuid.uuid4(),
            registry_id=None,
            pack_id="p1",
            name="Pack One",
            description="desc",
            version="1.0.0",
            author=None,
            tags=["docker"],
            manifest_sha=None,
            readme=None,
            installed_version="1.0.0",
            installed_at=now,
            created_at=now,
            updated_at=now,
        )
        m2 = TemplatePackModel(
            id=uuid.uuid4(),
            registry_id=uuid.uuid4(),
            pack_id="p2",
            name="Other",
            description=None,
            version="2.0.0",
            author=None,
            tags=[],
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        # tag filter – returns both then python filters to 1
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m1, m2]
        mock_session.execute.return_value = mock_result
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        page = await gateway.list_packs(PackListQueryDTO(tag="docker"))
        assert page.total == 1
        mock_result.scalars.return_value.all.return_value = [m1, m2]
        mock_session.execute.return_value = mock_result
        page2 = await gateway.list_packs(PackListQueryDTO(search="other"))
        assert page2.total == 1
        # installed filter uses SQL – mock should return filtered
        mock_installed = MagicMock()
        mock_installed.scalars.return_value.all.return_value = [m1]
        mock_session.execute.return_value = mock_installed
        page3 = await gateway.list_packs(PackListQueryDTO(installed=True))
        assert page3.total == 1
        mock_not = MagicMock()
        mock_not.scalars.return_value.all.return_value = [m2]
        mock_session.execute.return_value = mock_not
        page4 = await gateway.list_packs(PackListQueryDTO(installed=False))
        assert page4.total == 1

    async def test_template_pack_gateway_stats(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.models.template_pack import TemplatePackModel

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        now = datetime.now(UTC)
        m = TemplatePackModel(
            id=uuid.uuid4(),
            registry_id=uuid.uuid4(),
            pack_id="p1",
            name="N",
            description=None,
            version="1.0.0",
            author=None,
            tags=[],
            manifest_sha=None,
            readme=None,
            installed_version="1.0.0",
            installed_at=now,
            created_at=now,
            updated_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [m]
        mock_session.execute.return_value = mock_result
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        stats = await gateway.get_stats(group_by="registry_id")
        assert stats.total == 1
        stats2 = await gateway.get_stats(group_by=None)
        assert stats2.total == 1

    async def test_template_pack_gateway_install_uninstall(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.models.template_pack import TemplatePackModel

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        pid = uuid.uuid4()
        now = datetime.now(UTC)
        model = TemplatePackModel(
            id=pid,
            registry_id=None,
            pack_id="p1",
            name="N",
            description=None,
            version="1.0.0",
            author=None,
            tags=[],
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        mock_session.get = AsyncMock(return_value=model)
        # mock command/script name queries
        mock_cmd = MagicMock()
        mock_cmd.all.return_value = []
        mock_scr = MagicMock()
        mock_scr.all.return_value = []
        # first call for cmd names, second for scr names
        mock_session.execute = AsyncMock(side_effect=[mock_cmd, mock_scr])
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        res = await gateway.install_pack(pid, on_conflict="fail")
        assert res.pack_id == pid
        # already installed case
        model.installed_version = "1.0.0"
        mock_session.get.return_value = model
        mock_session.execute = AsyncMock(side_effect=[mock_cmd, mock_scr])
        with pytest.raises(Exception):  # PackConflictError
            await gateway.install_pack(pid)
        # not found
        mock_session.get.return_value = None
        with pytest.raises(Exception):
            await gateway.install_pack(uuid.uuid4())
        # uninstall
        model.installed_version = "1.0.0"
        mock_session.get.return_value = model
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        await gateway.uninstall_pack(pid)
        assert model.installed_version is None
        # uninstall not found
        mock_session.get.return_value = None
        with pytest.raises(Exception):
            await gateway.uninstall_pack(uuid.uuid4())

    async def test_template_pack_gateway_list_installations(self) -> None:
        from app.adapters.persistence.template_pack import SqlAlchemyTemplatePackGateway
        from app.models.template_installation import TemplateInstallationModel
        from app.models.template_pack import TemplatePackModel

        mock_maker, mock_session, _ = _make_mock_sessionmaker()
        pid = uuid.uuid4()
        now = datetime.now(UTC)
        pack = TemplatePackModel(
            id=pid,
            registry_id=None,
            pack_id="p1",
            name="N",
            description=None,
            version="1.0.0",
            author=None,
            tags=[],
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        mock_session.get = AsyncMock(return_value=pack)
        inst = TemplateInstallationModel(
            id=uuid.uuid4(),
            pack_id=pid,
            entity_type="command",
            entity_id=uuid.uuid4(),
            created_at=now,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [inst]
        mock_session.execute.return_value = mock_result
        gateway = SqlAlchemyTemplatePackGateway(sessionmaker=mock_maker)  # type: ignore[arg-type]
        page = await gateway.list_installations(pid, offset=0, limit=10)
        assert page.total == 1
        # not found
        mock_session.get.return_value = None
        with pytest.raises(Exception):
            await gateway.list_installations(uuid.uuid4(), offset=0, limit=10)


class TestComposeApiVerbBulk:
    async def test_compose_verb_bulk_endpoints(self) -> None:
        from app.application.dto.compose import (
            ComposeBulkResultDTO,
            ComposeServiceResultDTO,
        )

        mock_service = AsyncMock(spec=ComposeService)
        nid = uuid.uuid4()
        bulk = ComposeBulkResultDTO(
            total=1,
            succeeded=1,
            failed=0,
            results=(
                ComposeServiceResultDTO(service="web", status="success", output="ok"),
            ),
        )
        bulk_mixed = ComposeBulkResultDTO(
            total=2,
            succeeded=1,
            failed=1,
            results=(
                ComposeServiceResultDTO(service="web", status="success", output="ok"),
                ComposeServiceResultDTO(service="db", status="error", error="fail"),
            ),
        )
        mock_service.verb_bulk.return_value = bulk
        mock_service.up.return_value = bulk
        mock_service.down.return_value = "down"
        mock_service.ps.return_value = MagicMock(output="ps", containers=())
        mock_service.logs.return_value = "logs"
        mock_service.config.return_value = "config"
        mock_service.images.return_value = (["nginx"], "out")
        mock_service.top.return_value = (["PID"], [["1"]], "out")
        mock_service.port.return_value = "0.0.0.0:8080"
        mock_service.version.return_value = ("v2", "out")
        mock_service.exec.return_value = ("out", "", 0)
        mock_service.run.return_value = "run out"
        app = _create_compose_app(mock_service)
        headers = {"X-API-Key": "test-master"}
        with patch(
            "app.api.deps.get_settings", return_value=_mock_settings("test-master")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers=headers,
            ) as client:
                for path in [
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/starts",
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/pauses",
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/unpauses",
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/creates",
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/pulls",
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/pushs",
                ]:
                    resp = await client.post(path, json={"services": ["web"]})
                    assert resp.status_code in (200, 207)
                # stops and restarts with timeout query
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/stops?timeout=10",
                    json={"services": ["web"]},
                )
                assert resp.status_code in (200, 207)
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/restarts?timeout=10",
                    json={"services": ["web"]},
                )
                assert resp.status_code in (200, 207)
                # kills
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/kills",
                    json={"signal": "SIGTERM", "services": ["web"]},
                )
                assert resp.status_code in (200, 207)
                # rms with volumes
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/rms?volumes=true",
                    json={"services": ["web"]},
                )
                assert resp.status_code in (200, 207)
                # builds with no_cache
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/builds?no_cache=true",
                    json={"services": ["web"]},
                )
                assert resp.status_code in (200, 207)
                # 207 mixed
                mock_service.verb_bulk.return_value = bulk_mixed
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/starts",
                    json={"services": ["web", "db"]},
                )
                assert resp.status_code == 207
                # ups/downs already tested but cover again
                mock_service.up.return_value = bulk_mixed
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/ups",
                    json={"pull": False, "build": False},
                )
                assert resp.status_code == 207
                # get endpoints
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/ps"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/logs?tail=10"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/config"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/images"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/top"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/port?service=web&private_port=80"
                )
                assert resp.status_code == 200
                resp = await client.get(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/version"
                )
                assert resp.status_code == 200
                # exec/run
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/executions",
                    json={"service": "web", "command": "ls"},
                )
                assert resp.status_code == 200
                resp = await client.post(
                    f"/api/v2/nodes/{nid}/docker/compose/projects/proj/runs",
                    json={"service": "web", "command": "echo hi"},
                )
                assert resp.status_code == 200

    async def test_templates_extra_endpoints(self) -> None:
        from app.application.dto.template_pack import (
            PackAssetDTO,
            PackDetailDTO,
            PackInstallationDTO,
            PackInstallationPageDTO,
            PackStatsBucketDTO,
            PackStatsDTO,
            PackViewDTO,
        )
        from app.application.dto.template_registry import RegistryViewDTO

        mock_reg = AsyncMock()
        mock_pack = AsyncMock()
        now = datetime.now(UTC)
        pid = uuid.uuid4()
        view = PackViewDTO(
            id=pid,
            registry_id=None,
            pack_id="p1",
            name="N",
            description=None,
            version="1.0.0",
            author=None,
            tags=(),
            manifest_sha=None,
            readme=None,
            installed_version=None,
            installed_at=None,
            created_at=now,
            updated_at=now,
        )
        asset = PackAssetDTO(
            id=uuid.uuid4(),
            pack_id=pid,
            path="a",
            size=1,
            sha="s",
            created_at=now,
            updated_at=now,
        )
        detail = PackDetailDTO(pack=view, assets=(asset,), commands=(), scripts=())
        mock_pack.get_pack_detail.return_value = detail
        mock_pack.list_packs.return_value = MagicMock(items=(view,), total=1)
        mock_pack.get_assets_tar.return_value = b"tarbytes"
        mock_pack.get_stats.return_value = PackStatsDTO(
            total=1,
            installed=0,
            not_installed=1,
            buckets=(
                PackStatsBucketDTO(group="g", total=1, installed=0, not_installed=1),
            ),
        )
        mock_pack.list_installations.return_value = PackInstallationPageDTO(
            items=(
                PackInstallationDTO(
                    id=uuid.uuid4(),
                    pack_id=pid,
                    entity_type="command",
                    entity_id=uuid.uuid4(),
                    created_at=now,
                ),
            ),
            total=1,
        )
        mock_pack.uninstall_pack.return_value = None
        mock_pack.update_pack.return_value = MagicMock(
            pack_id=pid, version="1.0.0", total=1, succeeded=1, failed=0, results=()
        )
        mock_reg.get_registry.return_value = RegistryViewDTO(
            id=uuid.uuid4(),
            owner="o",
            name="n",
            default_branch="main",
            last_synced_at=None,
            created_at=now,
            updated_at=now,
        )
        app = _create_templates_app(mock_reg, mock_pack)
        headers = {"X-API-Key": "test-master"}
        with patch(
            "app.api.deps.get_settings", return_value=_mock_settings("test-master")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers=headers,
            ) as client:
                resp = await client.get(f"/api/v2/templates/packs/{pid}")
                assert resp.status_code == 200
                resp = await client.get("/api/v2/templates/packs?limit=10")
                assert resp.status_code == 200
                resp = await client.get("/api/v2/templates/packs?cursor=invalid")
                assert resp.status_code == 422
                resp = await client.get(f"/api/v2/templates/packs/{pid}/archive")
                assert resp.status_code == 200
                resp = await client.get("/api/v2/templates/packs/stats?group_by=tag")
                assert resp.status_code == 200
                resp = await client.get(f"/api/v2/templates/packs/{pid}/installations")
                assert resp.status_code == 200
                resp = await client.post(
                    f"/api/v2/templates/packs/{pid}/uninstallations"
                )
                assert resp.status_code == 204
                resp = await client.post(
                    f"/api/v2/templates/packs/{pid}/updates?on_conflict=rename"
                )
                assert resp.status_code in (200, 207)
                # delete registry
                rid = uuid.uuid4()
                mock_reg.delete_registry.return_value = None
                resp = await client.delete(f"/api/v2/templates/registries/{rid}")
                assert resp.status_code == 204
