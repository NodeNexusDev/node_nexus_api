"""Extra coverage for app/api/v2/compose.py remaining miss.

Covers POST create 201/409, GET ?cursor invalid 422, GET/PATCH/DELETE by name,
POST ups/downs with 207, bulk verbs starts/stops etc with 207,
GET ps/logs/config/images/top/port/version, POST executions/runs,
plus helpers _validate_project_name, _compose_file_path.
Uses AsyncMock, Dishka, httpx2. Keeps ruff/ty clean.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.api.v2.compose import (
    _bulk_to_response,
    _decode_offset,
    _encode_offset,
    _paginate_offset,
    _to_response,
    _validate_project_name,
)
from app.api.v2.compose import router as compose_router
from app.application.dto.compose import (
    ComposeBulkResultDTO,
    ComposePsDTO,
    ComposeServiceResultDTO,
    ComposeViewDTO,
)
from app.application.services.compose_service import ComposeService
from app.application.services.compose_service import (
    _compose_file_path as svc_compose_file_path,
)
from app.application.services.compose_service import (
    _validate_project_name as svc_validate,
)
from app.core.exceptions import (
    ComposeProjectAlreadyExistsError,
    ComposeProjectNotFoundError,
    DomainError,
)
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings

NODE_ID = uuid.uuid4()
PROJ = "myproj"
PROJ2 = "other-proj_1"
BAD_NAME = "bad!name"
LONG_NAME = "a" * 101
COMPOSE_YML = "version: '3'\nservices:\n  web:\n    image: nginx"

_SETTINGS_PATCH = patch(
    "app.api.deps.get_settings",
    return_value=_mock_settings("test-master"),
)


def _make_view(**overrides: object) -> ComposeViewDTO:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "node_id": NODE_ID,
        "project_name": PROJ,
        "compose": COMPOSE_YML,
        "env": {"FOO": "bar"},
        "template_pack_id": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return ComposeViewDTO(**defaults)  # type: ignore[arg-type]


def _make_bulk(
    succeeded: int,
    failed: int,
    services: list[str] | None = None,
) -> ComposeBulkResultDTO:
    svc_names = services or ["web", "db"]
    results: list[ComposeServiceResultDTO] = []
    for i in range(succeeded):
        results.append(
            ComposeServiceResultDTO(
                service=svc_names[i % len(svc_names)], status="success", output="ok"
            )
        )
    for i in range(failed):
        results.append(
            ComposeServiceResultDTO(
                service=svc_names[(succeeded + i) % len(svc_names)],
                status="error",
                error="fail",
            )
        )
    return ComposeBulkResultDTO(
        total=succeeded + failed,
        succeeded=succeeded,
        failed=failed,
        results=tuple(results),
    )


def _create_app(service_mock: AsyncMock | MagicMock | None = None) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(compose_router, prefix="/api/v2")
    svc = service_mock or AsyncMock(spec=ComposeService)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_compose_service(self) -> ComposeService:
            return as_typed_mock(ComposeService, svc)

    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_validate_project_name_ok(self) -> None:
        assert _validate_project_name("my-proj_1.2") == "my-proj_1.2"
        assert _validate_project_name("a") == "a"
        assert _validate_project_name("A1-._") == "A1-._"  # noqa: S101

    def test_validate_project_name_invalid(self) -> None:
        from fastapi import HTTPException

        for bad in ("", "bad/name", "-bad", ".bad", BAD_NAME, LONG_NAME):
            with pytest.raises(HTTPException) as ei:
                _validate_project_name(bad)
            assert ei.value.status_code == 422

    def test_svc_validate_ok(self) -> None:
        assert svc_validate("my-proj_1") == "my-proj_1"

    def test_svc_validate_invalid(self) -> None:
        for bad in ("", "bad/name", LONG_NAME):
            with pytest.raises(ValueError):
                svc_validate(bad)

    def test_compose_file_path(self) -> None:
        p = svc_compose_file_path("my-proj")
        assert p.startswith("/tmp/nn-compose-")
        assert p.endswith(".yml")
        p2 = svc_compose_file_path("bad/name with spaces")
        assert "bad_name_with_spaces" in p2
        p3 = svc_compose_file_path("a-b.c_d")
        assert p3 == "/tmp/nn-compose-a_b_c_d.yml" or "a_b" in p3

    def test_compose_file_path_sanitizes(self) -> None:
        assert svc_compose_file_path("proj!@#") == "/tmp/nn-compose-proj___.yml"

    def test_encode_decode_roundtrip(self) -> None:
        for off in (0, 1, 5, 100):
            cur = _encode_offset(off)
            assert _decode_offset(cur) == off

    def test_encode_is_base64_json(self) -> None:
        cur = _encode_offset(42)
        raw = base64.urlsafe_b64decode(cur.encode())
        data = json.loads(raw)
        assert data["offset"] == 42

    def test_decode_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid cursor"):
            _decode_offset("not-base64!!!")
        bad = base64.urlsafe_b64encode(json.dumps({"bad": 1}).encode()).decode()
        with pytest.raises(ValueError):
            _decode_offset(bad)
        bad2 = base64.urlsafe_b64encode(b"not-json").decode()
        with pytest.raises(ValueError):
            _decode_offset(bad2)

    def test_paginate_slice(self) -> None:
        items = list(range(10))
        sliced, nxt, has_more = _paginate_offset(items, None, 3)
        assert sliced == [0, 1, 2]
        assert has_more is True
        assert nxt is not None
        sliced2, nxt2, has2 = _paginate_offset(items, nxt, 3)
        assert sliced2 == [3, 4, 5]
        assert has2 is True
        assert nxt2 is not None

    def test_paginate_last_page(self) -> None:
        items = list(range(5))
        cur = _encode_offset(3)
        sliced, nxt, has_more = _paginate_offset(items, cur, 5)
        assert sliced == [3, 4]
        assert has_more is False
        assert nxt is None

    def test_paginate_invalid_cursor_422(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            _paginate_offset([1, 2, 3], "bad!!!", 2)
        assert ei.value.status_code == 422

    def test_to_response_maps(self) -> None:
        dto = _make_view()
        resp = _to_response(dto)
        assert resp.project_name == dto.project_name
        assert resp.compose == dto.compose
        assert resp.id == dto.id

    def test_bulk_to_response_maps(self) -> None:
        bulk = ComposeBulkResultDTO(
            total=2,
            succeeded=1,
            failed=1,
            results=(
                ComposeServiceResultDTO(service="web", status="success", output="ok"),
                ComposeServiceResultDTO(service="db", status="error", error="fail"),
            ),
        )
        res = _bulk_to_response(bulk)
        assert res.total == 2
        assert res.succeeded == 1
        assert res.failed == 1
        assert res.results[0].service == "web"
        assert res.results[1].status == "error"

    def test_bulk_to_response_all_success(self) -> None:
        bulk = _make_bulk(2, 0, ["web", "db"])
        res = _bulk_to_response(bulk)
        assert res.failed == 0
        assert res.succeeded == 2


# ---------------------------------------------------------------------------
# POST /projects create 201/409
# ---------------------------------------------------------------------------


class TestCreateProject:
    async def test_create_201(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        dto = _make_view(project_name=PROJ)
        svc.create_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={"project_name": PROJ, "compose": COMPOSE_YML},
                )
        assert resp.status_code == 201
        assert resp.json()["project_name"] == PROJ
        svc.create_project.assert_awaited_once()

    async def test_create_with_env_and_template(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        tid = uuid.uuid4()
        dto = _make_view(project_name=PROJ, env={"A": "b"}, template_pack_id=tid)
        svc.create_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={
                        "project_name": PROJ,
                        "compose": COMPOSE_YML,
                        "env": {"A": "b"},
                        "template_pack_id": str(tid),
                    },
                )
        assert resp.status_code == 201
        # ensure DTO had env tuple
        args = svc.create_project.call_args.args[0]
        assert args.env == (("A", "b"),)

    async def test_create_with_no_env(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        dto = _make_view(project_name=PROJ, env=None)
        svc.create_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={"project_name": PROJ, "compose": COMPOSE_YML},
                )
        assert resp.status_code == 201
        args = svc.create_project.call_args.args[0]
        assert args.env == ()

    async def test_create_409(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.create_project.side_effect = ComposeProjectAlreadyExistsError("exists")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={"project_name": PROJ, "compose": COMPOSE_YML},
                )
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"].lower()

    async def test_create_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={"project_name": BAD_NAME, "compose": COMPOSE_YML},
                )
        assert resp.status_code == 422
        svc.create_project.assert_not_awaited()

    async def test_create_long_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={"project_name": LONG_NAME, "compose": COMPOSE_YML},
                )
        assert resp.status_code == 422

    async def test_create_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.create_project.side_effect = ValueError("bad compose")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects",
                    json={"project_name": PROJ, "compose": COMPOSE_YML},
                )
        assert resp.status_code == 422
        assert "bad compose" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /projects ?cursor invalid 422 and pagination
# ---------------------------------------------------------------------------


class TestListProjects:
    async def test_list_no_cursor(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.list_all_projects.return_value = [
            _make_view(project_name="p1"),
            _make_view(project_name="p2"),
        ]
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/compose/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["limit"] == 20

    async def test_list_with_limit_and_cursor(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.list_all_projects.return_value = [
            _make_view(project_name=f"p{i}") for i in range(5)
        ]
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects?limit=2"
                )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2
        assert resp.json()["has_more"] is True
        assert resp.json()["next_cursor"] is not None
        cur = resp.json()["next_cursor"]
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp2 = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects?cursor={cur}&limit=2"
                )
        assert resp2.status_code == 200
        assert len(resp2.json()["items"]) == 2

    async def test_list_invalid_cursor_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.list_all_projects.return_value = []
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects?cursor=bad!!!"
                )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"

    async def test_list_empty(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.list_all_projects.return_value = []
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects?limit=10"
                )
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["has_more"] is False


# ---------------------------------------------------------------------------
# GET /projects/{name}
# ---------------------------------------------------------------------------


class TestGetProject:
    async def test_get_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        dto = _make_view(project_name=PROJ)
        svc.get_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}"
                )
        assert resp.status_code == 200
        assert resp.json()["project_name"] == PROJ

    async def test_get_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.get_project.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}"
                )
        assert resp.status_code == 404

    async def test_get_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}"
                )
        assert resp.status_code == 422
        svc.get_project.assert_not_awaited()

    async def test_get_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.get_project.side_effect = ValueError("bad name")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}"
                )
        assert resp.status_code == 422
        assert "bad name" in resp.json()["detail"]

    async def test_get_long_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{LONG_NAME}"
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /projects/{name}
# ---------------------------------------------------------------------------


class TestPatchProject:
    async def test_patch_success_compose_only(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        dto = _make_view(project_name=PROJ, compose="new")
        svc.update_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}",
                    json={"compose": "new"},
                )
        assert resp.status_code == 200
        assert resp.json()["compose"] == "new"

    async def test_patch_with_env(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        dto = _make_view(project_name=PROJ, env={"NEW": "val"})
        svc.update_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}",
                    json={"env": {"NEW": "val"}},
                )
        assert resp.status_code == 200
        args = svc.update_project.call_args.args[2]
        assert args.env == (("NEW", "val"),)
        assert args.has_env is True

    async def test_patch_env_none(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        dto = _make_view(project_name=PROJ)
        svc.update_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}",
                    json={"compose": "x"},
                )
        assert resp.status_code == 200
        args = svc.update_project.call_args.args[2]
        assert args.has_env is False

    async def test_patch_with_template_pack(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        tid = uuid.uuid4()
        dto = _make_view(project_name=PROJ, template_pack_id=tid)
        svc.update_project.return_value = dto
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}",
                    json={"template_pack_id": str(tid)},
                )
        assert resp.status_code == 200
        args = svc.update_project.call_args.args[2]
        assert args.has_template_pack_id is True

    async def test_patch_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.update_project.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}",
                    json={"compose": "new"},
                )
        assert resp.status_code == 404

    async def test_patch_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}",
                    json={"compose": "new"},
                )
        assert resp.status_code == 422
        svc.update_project.assert_not_awaited()

    async def test_patch_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.update_project.side_effect = ValueError("bad compose")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}",
                    json={"compose": "new"},
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /projects/{name}
# ---------------------------------------------------------------------------


class TestDeleteProject:
    async def test_delete_204(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.delete_project.return_value = None
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}"
                )
        assert resp.status_code == 204
        svc.delete_project.assert_awaited_once_with(NODE_ID, PROJ)

    async def test_delete_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.delete_project.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}"
                )
        assert resp.status_code == 404

    async def test_delete_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}"
                )
        assert resp.status_code == 422
        svc.delete_project.assert_not_awaited()

    async def test_delete_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.delete_project.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}"
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /ups with 207 and /downs
# ---------------------------------------------------------------------------


class TestComposeUp:
    async def test_up_all_success_200(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.up.return_value = _make_bulk(2, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ups",
                    json={},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 2
        svc.up.assert_awaited_once_with(
            NODE_ID, PROJ, pull=False, build=False, services=None
        )

    async def test_up_all_failed_200(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.up.return_value = _make_bulk(0, 2)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ups",
                    json={},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 2

    async def test_up_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.up.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ups",
                    json={"pull": True, "build": True, "services": ["web"]},
                )
        assert resp.status_code == 207
        svc.up.assert_awaited_once_with(
            NODE_ID, PROJ, pull=True, build=True, services=["web"]
        )

    async def test_up_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.up.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ups",
                    json={},
                )
        assert resp.status_code == 404

    async def test_up_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/ups",
                    json={},
                )
        assert resp.status_code == 422
        svc.up.assert_not_awaited()

    async def test_up_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.up.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ups",
                    json={},
                )
        assert resp.status_code == 422


class TestComposeDown:
    async def test_down_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.down.return_value = "removed"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/downs",
                    json={},
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "removed"
        assert resp.json()["status"] == "down"

    async def test_down_with_params(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.down.return_value = "done"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/downs",
                    json={
                        "volumes": True,
                        "remove_orphans": True,
                        "timeout": 30,
                        "images": "all",
                    },
                )
        assert resp.status_code == 200
        svc.down.assert_awaited_once_with(
            NODE_ID, PROJ, volumes=True, remove_orphans=True, timeout=30, images="all"
        )

    async def test_down_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.down.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/downs",
                    json={},
                )
        assert resp.status_code == 404

    async def test_down_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/downs",
                    json={},
                )
        assert resp.status_code == 422

    async def test_down_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.down.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/downs",
                    json={},
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Bulk verbs with 207
# ---------------------------------------------------------------------------


class TestStarts:
    async def test_starts_success_200(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0, ["web"])
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/starts",
                    json={"services": ["web"]},
                )
        assert resp.status_code == 200
        svc.verb_bulk.assert_awaited_once_with(NODE_ID, PROJ, "start", ["web"])

    async def test_starts_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/starts",
                    json={},
                )
        assert resp.status_code == 207

    async def test_starts_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/starts",
                    json={},
                )
        assert resp.status_code == 404

    async def test_starts_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/starts",
                    json={},
                )
        assert resp.status_code == 422

    async def test_starts_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/starts",
                    json={},
                )
        assert resp.status_code == 422


class TestStops:
    async def test_stops_success_200(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/stops",
                    json={},
                )
        assert resp.status_code == 200
        # default timeout 10 => extra " -t 10"
        assert "stop" in svc.verb_bulk.call_args.args[2]
        assert svc.verb_bulk.call_args.kwargs.get("extra") == " -t 10"

    async def test_stops_with_timeout(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/stops?timeout=30",
                    json={"services": ["web"]},
                )
        assert resp.status_code == 200
        assert svc.verb_bulk.call_args.kwargs.get("extra") == " -t 30"

    async def test_stops_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/stops",
                    json={},
                )
        assert resp.status_code == 207

    async def test_stops_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("missing")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/stops",
                    json={},
                )
        assert resp.status_code == 404

    async def test_stops_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/stops",
                    json={},
                )
        assert resp.status_code == 422


class TestRestarts:
    async def test_restarts_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(2, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/restarts",
                    json={},
                )
        assert resp.status_code == 200

    async def test_restarts_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/restarts",
                    json={},
                )
        assert resp.status_code == 207

    async def test_restarts_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/restarts",
                    json={},
                )
        assert resp.status_code == 404

    async def test_restarts_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/restarts",
                    json={},
                )
        assert resp.status_code == 422

    async def test_restarts_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/restarts",
                    json={},
                )
        assert resp.status_code == 422


class TestPauses:
    async def test_pauses_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pauses",
                    json={},
                )
        assert resp.status_code == 200

    async def test_pauses_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pauses",
                    json={},
                )
        assert resp.status_code == 207

    async def test_pauses_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pauses",
                    json={},
                )
        assert resp.status_code == 404

    async def test_pauses_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pauses",
                    json={},
                )
        assert resp.status_code == 422


class TestUnpauses:
    async def test_unpauses_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/unpauses",
                    json={},
                )
        assert resp.status_code == 200

    async def test_unpauses_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/unpauses",
                    json={},
                )
        assert resp.status_code == 207

    async def test_unpauses_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/unpauses",
                    json={},
                )
        assert resp.status_code == 404

    async def test_unpauses_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/unpauses",
                    json={},
                )
        assert resp.status_code == 422


class TestKills:
    async def test_kills_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/kills",
                    json={"signal": "SIGKILL"},
                )
        assert resp.status_code == 200
        assert svc.verb_bulk.call_args.kwargs.get("extra") == " -s SIGKILL"

    async def test_kills_default_signal(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/kills",
                    json={},
                )
        # default signal SIGTERM => extra " -s SIGTERM"
        assert resp.status_code == 200

    async def test_kills_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/kills",
                    json={"signal": "SIGTERM"},
                )
        assert resp.status_code == 207

    async def test_kills_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/kills",
                    json={"signal": "SIGTERM"},
                )
        assert resp.status_code == 404

    async def test_kills_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/kills",
                    json={"signal": "SIGTERM"},
                )
        assert resp.status_code == 422


class TestCreates:
    async def test_creates_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/creates",
                    json={},
                )
        assert resp.status_code == 200

    async def test_creates_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/creates",
                    json={},
                )
        assert resp.status_code == 207

    async def test_creates_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/creates",
                    json={},
                )
        assert resp.status_code == 404

    async def test_creates_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/creates",
                    json={},
                )
        assert resp.status_code == 422


class TestRms:
    async def test_rms_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/rms",
                    json={},
                )
        assert resp.status_code == 200
        # default extra " -f"
        assert svc.verb_bulk.call_args.kwargs.get("extra") == " -f"

    async def test_rms_with_volumes(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/rms?volumes=true",
                    json={},
                )
        assert resp.status_code == 200
        assert svc.verb_bulk.call_args.kwargs.get("extra") == " -f -v"

    async def test_rms_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/rms",
                    json={},
                )
        assert resp.status_code == 207

    async def test_rms_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/rms",
                    json={},
                )
        assert resp.status_code == 404

    async def test_rms_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/rms",
                    json={},
                )
        assert resp.status_code == 422


class TestPulls:
    async def test_pulls_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pulls",
                    json={},
                )
        assert resp.status_code == 200

    async def test_pulls_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pulls",
                    json={},
                )
        assert resp.status_code == 207

    async def test_pulls_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pulls",
                    json={},
                )
        assert resp.status_code == 404

    async def test_pulls_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pulls",
                    json={},
                )
        assert resp.status_code == 422


class TestPushs:
    async def test_pushs_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pushs",
                    json={},
                )
        assert resp.status_code == 200

    async def test_pushs_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pushs",
                    json={},
                )
        assert resp.status_code == 207

    async def test_pushs_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pushs",
                    json={},
                )
        assert resp.status_code == 404

    async def test_pushs_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/pushs",
                    json={},
                )
        assert resp.status_code == 422


class TestBuilds:
    async def test_builds_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/builds",
                    json={},
                )
        assert resp.status_code == 200
        assert svc.verb_bulk.call_args.kwargs.get("extra") == ""

    async def test_builds_with_no_cache(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/builds?no_cache=true",
                    json={},
                )
        assert resp.status_code == 200
        assert svc.verb_bulk.call_args.kwargs.get("extra") == " --no-cache"

    async def test_builds_partial_207(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.return_value = _make_bulk(1, 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/builds",
                    json={},
                )
        assert resp.status_code == 207

    async def test_builds_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/builds",
                    json={},
                )
        assert resp.status_code == 404

    async def test_builds_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.verb_bulk.side_effect = ValueError("e")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/builds",
                    json={},
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET ps / logs / config / images / top / port / version
# ---------------------------------------------------------------------------


class TestPs:
    async def test_ps_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.ps.return_value = ComposePsDTO(output="ps out", containers=({"ID": "abc"},))
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ps"
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "ps out"

    async def test_ps_with_all(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.ps.return_value = ComposePsDTO(output="x", containers=())
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ps?all=true"
                )
        assert resp.status_code == 200
        svc.ps.assert_awaited_once_with(NODE_ID, PROJ, all=True)

    async def test_ps_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.ps.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ps"
                )
        assert resp.status_code == 404

    async def test_ps_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/ps"
                )
        assert resp.status_code == 422

    async def test_ps_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.ps.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/ps"
                )
        assert resp.status_code == 422


class TestLogs:
    async def test_logs_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.logs.return_value = "log line"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/logs"
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "log line"
        assert resp.json()["logs"] == "log line"

    async def test_logs_with_params(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.logs.return_value = "out"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/logs?tail=50&since=2024-01-01&services=web"
                )
        assert resp.status_code == 200
        svc.logs.assert_awaited_once_with(
            NODE_ID, PROJ, tail=50, since="2024-01-01", services="web"
        )

    async def test_logs_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.logs.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/logs"
                )
        assert resp.status_code == 404

    async def test_logs_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/logs"
                )
        assert resp.status_code == 422

    async def test_logs_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.logs.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/logs"
                )
        assert resp.status_code == 422


class TestConfig:
    async def test_config_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.config.return_value = "resolved yaml"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/config"
                )
        assert resp.status_code == 200
        assert resp.json()["config"] == "resolved yaml"

    async def test_config_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.config.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/config"
                )
        assert resp.status_code == 404

    async def test_config_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/config"
                )
        assert resp.status_code == 422

    async def test_config_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.config.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/config"
                )
        assert resp.status_code == 422


class TestImages:
    async def test_images_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.images.return_value = (["nginx", "redis"], "raw out")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/images"
                )
        assert resp.status_code == 200
        assert resp.json()["images"] == ["nginx", "redis"]
        assert resp.json()["output"] == "raw out"

    async def test_images_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.images.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/images"
                )
        assert resp.status_code == 404

    async def test_images_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/images"
                )
        assert resp.status_code == 422

    async def test_images_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.images.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/images"
                )
        assert resp.status_code == 422


class TestTop:
    async def test_top_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.top.return_value = (["PID", "USER"], [["1", "root"]], "raw")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/top"
                )
        assert resp.status_code == 200
        assert resp.json()["titles"] == ["PID", "USER"]

    async def test_top_with_service(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.top.return_value = (["PID"], [["1"]], "out")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/top?service=web"
                )
        assert resp.status_code == 200
        svc.top.assert_awaited_once_with(NODE_ID, PROJ, service="web")

    async def test_top_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.top.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/top"
                )
        assert resp.status_code == 404

    async def test_top_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/top"
                )
        assert resp.status_code == 422

    async def test_top_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.top.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/top"
                )
        assert resp.status_code == 422


class TestPort:
    async def test_port_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.port.return_value = "0.0.0.0:8080"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/port?service=web&private_port=80"
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "0.0.0.0:8080"
        assert resp.json()["bindings"] == "0.0.0.0:8080"

    async def test_port_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.port.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/port?service=web&private_port=80"
                )
        assert resp.status_code == 404

    async def test_port_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/port?service=web&private_port=80"
                )
        assert resp.status_code == 422

    async def test_port_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.port.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/port?service=web&private_port=80"
                )
        assert resp.status_code == 422


class TestVersion:
    async def test_version_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.version.return_value = ("v2.20.0", "v2.20.0")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/version"
                )
        assert resp.status_code == 200
        assert resp.json()["version"] == "v2.20.0"

    async def test_version_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.version.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/version"
                )
        assert resp.status_code == 404

    async def test_version_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/version"
                )
        assert resp.status_code == 422

    async def test_version_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.version.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/version"
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST executions / runs
# ---------------------------------------------------------------------------


class TestExecutions:
    async def test_exec_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.exec.return_value = ("out", "", 0)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/executions",
                    json={"service": "web", "command": "ls"},
                )
        assert resp.status_code == 200
        assert resp.json()["stdout"] == "out"
        assert resp.json()["exit_code"] == 0
        svc.exec.assert_awaited_once_with(
            NODE_ID, PROJ, service="web", command="ls", timeout=30
        )

    async def test_exec_with_timeout(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.exec.return_value = ("o", "e", 1)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/executions",
                    json={"service": "web", "command": "ls", "timeout": 60},
                )
        assert resp.status_code == 200
        svc.exec.assert_awaited_once_with(
            NODE_ID, PROJ, service="web", command="ls", timeout=60
        )

    async def test_exec_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.exec.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/executions",
                    json={"service": "web", "command": "ls"},
                )
        assert resp.status_code == 404

    async def test_exec_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/executions",
                    json={"service": "web", "command": "ls"},
                )
        assert resp.status_code == 422

    async def test_exec_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.exec.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/executions",
                    json={"service": "web", "command": "ls"},
                )
        assert resp.status_code == 422


class TestRuns:
    async def test_run_success(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.run.return_value = "run out"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/runs",
                    json={"service": "web", "command": "echo hi"},
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "run out"

    async def test_run_detached(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.run.return_value = "detached"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/runs",
                    json={"service": "web", "detached": True},
                )
        assert resp.status_code == 200
        svc.run.assert_awaited_once_with(
            NODE_ID, PROJ, service="web", command=None, detached=True, timeout=60
        )

    async def test_run_with_command_and_timeout(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.run.return_value = "out"
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/runs",
                    json={"service": "web", "command": "ls", "timeout": 120},
                )
        assert resp.status_code == 200
        svc.run.assert_awaited_once()

    async def test_run_404(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.run.side_effect = ComposeProjectNotFoundError("x")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/runs",
                    json={"service": "web"},
                )
        assert resp.status_code == 404

    async def test_run_invalid_name_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{BAD_NAME}/runs",
                    json={"service": "web"},
                )
        assert resp.status_code == 422

    async def test_run_value_error_422(self) -> None:
        svc = AsyncMock(spec=ComposeService)
        svc.run.side_effect = ValueError("bad")
        app = _create_app(svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/compose/projects/{PROJ}/runs",
                    json={"service": "web"},
                )
        assert resp.status_code == 422
