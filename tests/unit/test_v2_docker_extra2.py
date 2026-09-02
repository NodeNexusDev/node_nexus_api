"""Extra coverage for app/api/v2/docker.py remaining 213 miss.

Covers bulk vert endpoints (207), single kill/update/archive/port/wait,
images/networks/volumes bulk, system version/prune, cursor pagination
and invalid container_id 422. Uses AsyncMock, Dishka, httpx2.
Keeps ruff/ty clean.
"""

from __future__ import annotations

import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.error_mapping import domain_error_handler
from app.api.v2.docker import (
    _decode_offset,
    _encode_offset,
    _paginate_offset,
)
from app.api.v2.docker import (
    router as v2_docker_router,
)
from app.application.dto.docker import (
    ContainerCreatedDTO,
    DockerContainerConfigDTO,
    DockerContainerDTO,
    DockerContainerInspectDTO,
    DockerContainerStateDTO,
    DockerImageDTO,
    DockerNetworkDTO,
    DockerNetworkInspectDTO,
    DockerPruneResultDTO,
    DockerPullResultDTO,
    DockerStatsDTO,
    DockerSystemInfoDTO,
    DockerSystemVersionDTO,
    DockerVolumeDTO,
    DockerVolumeInspectDTO,
)
from app.application.services.docker.container_service import DockerContainerService
from app.application.services.docker.image_service import DockerImageService
from app.application.services.docker.resource_service import DockerResourceService
from app.application.services.docker.system_service import DockerSystemService
from app.core.exceptions import DomainError
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings

NODE_ID = uuid.uuid4()
CID = "abc123def456"
CID2 = "def456abc789"
CID3 = "abc789def012"
IMG = "nginx:latest"
IMG2 = "redis:7"
BAD_ID = "bad;id"
VOL = "myvol1"
NET = "net123"

_SETTINGS_PATCH = patch(
    "app.api.deps.get_settings",
    return_value=_mock_settings("test-master"),
)


def _create_v2_docker_app(
    *,
    container_service: AsyncMock | MagicMock | None = None,
    image_service: AsyncMock | MagicMock | None = None,
    resource_service: AsyncMock | MagicMock | None = None,
    system_service: AsyncMock | MagicMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(v2_docker_router, prefix="/api/v2")

    c_svc = container_service or AsyncMock(spec=DockerContainerService)
    i_svc = image_service or AsyncMock(spec=DockerImageService)
    r_svc = resource_service or AsyncMock(spec=DockerResourceService)
    s_svc = system_service or AsyncMock(spec=DockerSystemService)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_container_service(self) -> DockerContainerService:
            return as_typed_mock(DockerContainerService, c_svc)

        @provide(scope=Scope.REQUEST)
        def get_image_service(self) -> DockerImageService:
            return as_typed_mock(DockerImageService, i_svc)

        @provide(scope=Scope.REQUEST)
        def get_resource_service(self) -> DockerResourceService:
            return as_typed_mock(DockerResourceService, r_svc)

        @provide(scope=Scope.REQUEST)
        def get_system_service(self) -> DockerSystemService:
            return as_typed_mock(DockerSystemService, s_svc)

    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


def _container_dto(cid: str = CID) -> DockerContainerDTO:
    return DockerContainerDTO(
        id=cid,
        names="/web",
        image="nginx:latest",
        command="nginx",
        created_at="2026-01-01",
        state="running",
        status="Up 5 days",
        ports=None,
        networks=None,
    )


def _inspect_dto(cid: str = CID) -> DockerContainerInspectDTO:
    return DockerContainerInspectDTO(
        id=cid,
        name="/web",
        state=DockerContainerStateDTO(status="running", running=True, exit_code=0),
        config=DockerContainerConfigDTO(image="nginx:latest"),
        network_settings=(("Networks", {"bridge": {}}),),
    )


def _stats_dto(cid: str = CID) -> DockerStatsDTO:
    return DockerStatsDTO(
        container_id=cid,
        name="web",
        cpu_percent="1.23%",
        mem_usage="100MiB",
        mem_percent="5.0%",
        net_io="1MB / 2MB",
        block_io="0B / 0B",
        mem_limit=None,
        pids="1",
    )


def _exec_dto(exit_code: int = 0):  # type: ignore[no-untyped-def]
    # reuse for exec? Actually exec returns DockerExecResultDTO
    from app.application.dto.docker import DockerExecResultDTO

    return DockerExecResultDTO(
        stdout="out",
        stderr="" if exit_code == 0 else "err",
        exit_code=exit_code,
    )


def _pull_dto(image: str = IMG, success: bool = True) -> DockerPullResultDTO:
    return DockerPullResultDTO(
        image=image,
        output="pulled" if success else "failed",
        success=success,
    )


def _image_dto() -> DockerImageDTO:
    return DockerImageDTO(
        repository="nginx",
        tag="latest",
        id="abc123",
        size="187MB",
        created_at="2025-07-01",
    )


def _network_dto() -> DockerNetworkDTO:
    return DockerNetworkDTO(id=NET, name="bridge", driver="bridge", scope="local")


def _volume_dto() -> DockerVolumeDTO:
    return DockerVolumeDTO(driver="local", name=VOL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestDockerHelpers:
    def test_encode_decode_roundtrip(self) -> None:
        for offset in (0, 1, 20, 100):
            cur = _encode_offset(offset)
            assert _decode_offset(cur) == offset

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

    def test_paginate_invalid_cursor_raises_422(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            _paginate_offset([1, 2, 3], "bad!!!", 2)
        assert ei.value.status_code == 422


# ---------------------------------------------------------------------------
# Cursor pagination for lists
# ---------------------------------------------------------------------------


class TestListPagination:
    async def test_containers_no_cursor(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.list_containers.return_value = [_container_dto(CID), _container_dto(CID2)]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/containers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["limit"] == 20
        assert data["next_cursor"] is None

    async def test_containers_with_cursor_and_limit(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.list_containers.return_value = [_container_dto(str(i)) for i in range(5)]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers?limit=2"
                )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2
        assert resp.json()["has_more"] is True
        assert resp.json()["next_cursor"] is not None
        cur = resp.json()["next_cursor"]
        # second page
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp2 = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers?cursor={cur}&limit=2"
                )
        assert resp2.status_code == 200
        assert len(resp2.json()["items"]) == 2

    async def test_containers_invalid_cursor_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.list_containers.return_value = []
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers?cursor=bad!!!"
                )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"

    async def test_images_pagination(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.list_images.return_value = [_image_dto(), _image_dto()]
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/images?limit=1")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        assert resp.json()["has_more"] is True

    async def test_images_invalid_cursor(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.list_images.return_value = []
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/images?cursor=bad!!!"
                )
        assert resp.status_code == 422

    async def test_networks_pagination(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.list_networks.return_value = [_network_dto()]
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/networks")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    async def test_volumes_pagination(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.list_volumes.return_value = [_volume_dto(), _volume_dto()]
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/volumes?limit=1")
        assert resp.status_code == 200
        assert resp.json()["has_more"] is True

    async def test_networks_invalid_cursor(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.list_networks.return_value = []
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks?cursor=bad!!!"
                )
        assert resp.status_code == 422

    async def test_volumes_invalid_cursor(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.list_volumes.return_value = []
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/volumes?cursor=bad!!!"
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Bulk vert: containers starts..stats (207)
# ---------------------------------------------------------------------------


class TestBulkContainersStarts:
    async def test_all_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.start_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/starts",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)

        async def _start(nid, cid):  # noqa: ANN001
            if cid == CID:
                return None
            raise RuntimeError("boom")

        svc.start_container.side_effect = _start
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/starts",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207
        assert resp.json()["succeeded"] == 1
        assert resp.json()["failed"] == 1

    async def test_invalid_id_bulk_error(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.start_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/starts",
                    json={"container_ids": [BAD_ID]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1
        assert resp.json()["results"][0]["status"] == "error"


class TestBulkStops:
    async def test_all_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.stop_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/stops",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.stop_container.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/stops",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207


class TestBulkRestarts:
    async def test_all_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.restart_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/restarts",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.restart_container.side_effect = [None, RuntimeError("x")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/restarts",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207


class TestBulkRemovals:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.remove_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/removals",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.remove_container.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/removals",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207


class TestBulkPauses:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.pause_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/pauses",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.pause_container.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/pauses",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207


class TestBulkUnpauses:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.unpause_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/unpauses",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.unpause_container.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/unpauses",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207


class TestBulkKills:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.kill_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/kills",
                    json={"container_ids": [CID], "signal": "SIGKILL"},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.kill_container.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/kills",
                    json={"container_ids": [CID, CID2], "signal": "SIGTERM"},
                )
        assert resp.status_code == 207


class TestBulkUpdates:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.update_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/updates",
                    json={"container_ids": [CID], "memory": "512m"},
                )
        assert resp.status_code == 200

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.update_container.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/updates",
                    json={"container_ids": [CID, CID2], "cpus": "1.5"},
                )
        assert resp.status_code == 207


class TestBulkExecutions:
    async def test_all_success_exit_0(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        from app.application.dto.docker import DockerExecResultDTO

        svc.exec_command.return_value = DockerExecResultDTO(
            stdout="hello", stderr="", exit_code=0
        )
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/executions",
                    json={"container_ids": [CID], "command": "echo hi"},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1
        assert resp.json()["results"][0]["status"] == "success"
        assert resp.json()["results"][0]["exit_code"] == 0

    async def test_exit_nonzero_is_error(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        from app.application.dto.docker import DockerExecResultDTO

        svc.exec_command.return_value = DockerExecResultDTO(
            stdout="", stderr="err", exit_code=1
        )
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/executions",
                    json={"container_ids": [CID], "command": "false"},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1
        assert resp.json()["results"][0]["status"] == "error"

    async def test_partial_207_mixed(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        from app.application.dto.docker import DockerExecResultDTO

        svc.exec_command.side_effect = [
            DockerExecResultDTO(stdout="ok", stderr="", exit_code=0),
            RuntimeError("boom"),
        ]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/executions",
                    json={"container_ids": [CID, CID2], "command": "echo hi"},
                )
        assert resp.status_code == 207
        assert resp.json()["succeeded"] == 1
        assert resp.json()["failed"] == 1


class TestBulkInspections:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_container.return_value = _inspect_dto(CID)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/inspections",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1
        assert resp.json()["results"][0]["data"]["Id"] == CID

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_container.side_effect = [_inspect_dto(CID), RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/inspections",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207

    async def test_invalid_id_error(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_container.return_value = _inspect_dto(CID)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/inspections",
                    json={"container_ids": [BAD_ID]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1


class TestBulkLogs:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_logs.return_value = "log line"
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/logs",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["logs"] == "log line"

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_logs.side_effect = ["ok", RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/logs",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207


class TestBulkStats207:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_stats.return_value = _stats_dto(CID)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/stats",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1
        assert resp.json()["results"][0]["stats"]["Container"] == CID

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_stats.side_effect = [_stats_dto(CID), RuntimeError("fail")]
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/stats",
                    json={"container_ids": [CID, CID2]},
                )
        assert resp.status_code == 207

    async def test_all_failed(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_stats.side_effect = RuntimeError("boom")
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/stats",
                    json={"container_ids": [CID]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1


# ---------------------------------------------------------------------------
# Single endpoints: kill / update / archive / port / wait
# ---------------------------------------------------------------------------


class TestSingleKill:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.kill_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/kill",
                    json={"signal": "SIGTERM"},
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "killed"
        svc.kill_container.assert_awaited_once_with(NODE_ID, CID, signal="SIGTERM")

    async def test_invalid_container_id_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/kill",
                    json={"signal": "SIGKILL"},
                )
        assert resp.status_code == 422
        svc.kill_container.assert_not_awaited()


class TestSingleUpdate:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.update_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/update",
                    json={"memory": "256m", "cpus": "0.5"},
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    async def test_invalid_container_id_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/update",
                    json={"memory": "128m"},
                )
        assert resp.status_code == 422


class TestSingleArchive:
    async def test_get_archive_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_archive.return_value = "file content"
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/archive?path=/etc/hosts"
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "file content"
        assert resp.json()["path"] == "/etc/hosts"

    async def test_put_archive_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.put_archive.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.put(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/archive?path=/tmp/foo&data=bar"
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "copied"

    async def test_get_archive_invalid_id_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/archive?path=/etc/hosts"
                )
        assert resp.status_code == 422


class TestSinglePort:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_port.return_value = "0.0.0.0:8080"
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/port"
                )
        assert resp.status_code == 200
        assert resp.json()["output"] == "0.0.0.0:8080"

    async def test_with_private_port(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_port.return_value = "0.0.0.0:8080"
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/port?private_port=80"
                )
        assert resp.status_code == 200
        svc.get_port.assert_awaited_once_with(NODE_ID, CID, private_port="80")

    async def test_invalid_id_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/port"
                )
        assert resp.status_code == 422


class TestSingleWait:
    async def test_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.wait_container.return_value = 0
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/wait"
                )
        assert resp.status_code == 200
        assert resp.json()["exit_code"] == 0

    async def test_with_timeout(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.wait_container.return_value = 1
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/wait?timeout=30"
                )
        assert resp.status_code == 200
        assert resp.json()["exit_code"] == 1
        svc.wait_container.assert_awaited_once_with(NODE_ID, CID, timeout=30)

    async def test_invalid_id_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/wait"
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Images / Networks / Volumes bulk (207)
# ---------------------------------------------------------------------------


class TestImagesBulk:
    async def test_pulls_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.pull_image.return_value = _pull_dto(IMG, True)
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/pulls",
                    json={"images": [IMG], "timeout": 300},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_pulls_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.pull_image.side_effect = [
            _pull_dto(IMG, True),
            RuntimeError("fail"),
        ]
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/pulls",
                    json={"images": [IMG, IMG2]},
                )
        assert resp.status_code == 207
        assert resp.json()["succeeded"] == 1
        assert resp.json()["failed"] == 1

    async def test_pulls_success_false_is_error(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.pull_image.return_value = _pull_dto(IMG, False)
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/pulls",
                    json={"images": [IMG]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1

    async def test_removals_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.remove_image.return_value = None
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/removals",
                    json={"image_ids": ["abc123"]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_removals_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.remove_image.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/removals",
                    json={"image_ids": ["img1", "img2"]},
                )
        assert resp.status_code == 207


class TestNetworksBulk:
    async def test_removals_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_network.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks/removals",
                    json={"network_ids": [NET]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_removals_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_network.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks/removals",
                    json={"network_ids": [NET, "net2"]},
                )
        assert resp.status_code == 207

    async def test_removals_invalid_id_error(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_network.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks/removals",
                    json={"network_ids": [BAD_ID]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1


class TestVolumesBulk:
    async def test_removals_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_volume.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/volumes/removals",
                    json={"volume_names": [VOL]},
                )
        assert resp.status_code == 200
        assert resp.json()["succeeded"] == 1

    async def test_removals_partial_207(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_volume.side_effect = [None, RuntimeError("fail")]
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/volumes/removals",
                    json={"volume_names": [VOL, "vol2"]},
                )
        assert resp.status_code == 207

    async def test_removals_invalid_name_error(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_volume.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/volumes/removals",
                    json={"volume_names": [BAD_ID]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1


# ---------------------------------------------------------------------------
# System: version / prune / df / info
# ---------------------------------------------------------------------------


class TestSystem:
    async def test_version_success(self) -> None:
        svc = AsyncMock(spec=DockerSystemService)
        svc.version.return_value = DockerSystemVersionDTO(
            server_version="27.0",
            api_version="1.45",
            go_version="go1.21",
            git_commit="abc",
            build_time="2026-01-01",
            os="linux",
            arch="amd64",
        )
        app = _create_v2_docker_app(system_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/system/version")
        assert resp.status_code == 200
        assert resp.json()["server_version"] == "27.0"
        assert resp.json()["api_version"] == "1.45"

    async def test_system_prune(self) -> None:
        svc = AsyncMock(spec=DockerSystemService)
        svc.system_prune.return_value = DockerPruneResultDTO(
            containers_deleted=("c1",),
            images_deleted=("i1",),
            space_reclaimed="10MB",
        )
        app = _create_v2_docker_app(system_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/system/prune?volumes=true"
                )
        assert resp.status_code == 200
        assert resp.json()["space_reclaimed"] == "10MB"

    async def test_prune_containers(self) -> None:
        svc = AsyncMock(spec=DockerSystemService)
        svc.prune_containers.return_value = DockerPruneResultDTO(
            containers_deleted=("c1", "c2"),
            space_reclaimed="5MB",
        )
        app = _create_v2_docker_app(system_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/nodes/{NODE_ID}/docker/containers/prune")
        assert resp.status_code == 200
        assert "c1" in resp.json()["containers_deleted"]

    async def test_prune_images(self) -> None:
        svc = AsyncMock(spec=DockerSystemService)
        svc.prune_images.return_value = DockerPruneResultDTO(
            images_deleted=("i1",),
            space_reclaimed="20MB",
        )
        app = _create_v2_docker_app(system_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/nodes/{NODE_ID}/docker/images/prune")
        assert resp.status_code == 200
        assert "i1" in resp.json()["images_deleted"]

    async def test_system_info(self) -> None:
        svc = AsyncMock(spec=DockerSystemService)
        svc.info.return_value = DockerSystemInfoDTO(
            server_version="27.0",
            storage_driver="overlay2",
            operating_system="Ubuntu",
            architecture="x86_64",
            total_memory="16GB",
            cpus=4,
            containers_running=2,
            containers_stopped=1,
            images=5,
        )
        app = _create_v2_docker_app(system_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/system/info")
        assert resp.status_code == 200
        assert resp.json()["server_version"] == "27.0"

    async def test_system_df(self) -> None:
        from app.application.dto.docker import DockerSystemDfDTO

        svc = AsyncMock(spec=DockerSystemService)
        svc.disk_usage.return_value = [
            DockerSystemDfDTO(
                type="Images",
                total_count=5,
                active_size="1GB",
                reclaimable_size="500MB",
                reclaimable_percent="50%",
            )
        ]
        app = _create_v2_docker_app(system_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/system/df")
        assert resp.status_code == 200
        assert resp.json()[0]["type"] == "Images"

    async def test_volumes_prune(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.prune_volumes.return_value = "reclaimed 10MB"
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/nodes/{NODE_ID}/docker/volumes/prune")
        assert resp.status_code == 200
        assert "10MB" in resp.json()["output"]

    async def test_networks_prune(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.prune_networks.return_value = "pruned"
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(f"/api/v2/nodes/{NODE_ID}/docker/networks/prune")
        assert resp.status_code == 200
        assert resp.json()["output"] == "pruned"


# ---------------------------------------------------------------------------
# Invalid container_id 422 for single endpoints (additional coverage)
# ---------------------------------------------------------------------------


class TestInvalidContainerId:
    async def test_get_container_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}"
                )
        assert resp.status_code == 422
        svc.get_container.assert_not_awaited()

    async def test_start_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/start"
                )
        assert resp.status_code == 422

    async def test_stop_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/stop"
                )
        assert resp.status_code == 422

    async def test_pause_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/pause"
                )
        assert resp.status_code == 422

    async def test_logs_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/logs"
                )
        assert resp.status_code == 422

    async def test_stats_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/stats"
                )
        assert resp.status_code == 422

    async def test_exec_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/exec",
                    json={"command": "ls"},
                )
        assert resp.status_code == 422

    async def test_top_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{BAD_ID}/top"
                )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Container create / inspect / rename / top (smoke for remaining lines)
# ---------------------------------------------------------------------------


class TestContainerCreateAndInspect:
    async def test_create_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.create_container.return_value = ContainerCreatedDTO(
            id=CID, name="myctr", image=IMG, status="created"
        )
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers",
                    json={"image": IMG},
                )
        assert resp.status_code == 201
        assert resp.json()["id"] == CID

    async def test_inspect_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_container.return_value = _inspect_dto(CID)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}")
        assert resp.status_code == 200
        assert resp.json()["Id"] == CID

    async def test_rename_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.rename_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/rename",
                    json={"new_name": "newname"},
                )
        assert resp.status_code == 200
        assert resp.json()["new_name"] == "newname"

    async def test_top_success(self) -> None:
        from app.application.dto.docker import DockerTopResultDTO

        svc = AsyncMock(spec=DockerContainerService)
        svc.top_container.return_value = DockerTopResultDTO(
            titles=("PID", "CMD"), processes=(("1", "sleep"),)
        )
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/top"
                )
        assert resp.status_code == 200
        assert resp.json()["titles"] == ["PID", "CMD"]


# ---------------------------------------------------------------------------
# Single container lifecycle remaining (204, logs, exec etc)
# ---------------------------------------------------------------------------


class TestSingleContainerLifecycle:
    async def test_start_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.start_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/start"
                )
        assert resp.status_code == 204
        svc.start_container.assert_awaited_once_with(NODE_ID, CID)

    async def test_stop_success_with_timeout(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.stop_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/stop?timeout=30"
                )
        assert resp.status_code == 204
        svc.stop_container.assert_awaited_once_with(NODE_ID, CID, timeout=30)

    async def test_restart_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.restart_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/restart"
                )
        assert resp.status_code == 204

    async def test_remove_success_with_force(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.remove_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}?force=true"
                )
        assert resp.status_code == 204
        svc.remove_container.assert_awaited_once_with(NODE_ID, CID, force=True)

    async def test_logs_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_logs.return_value = "log content"
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/logs?tail=50&since=123"
                )
        assert resp.status_code == 200
        assert resp.json() == "log content"
        svc.get_logs.assert_awaited_once_with(NODE_ID, CID, tail=50, since="123")

    async def test_exec_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        from app.application.dto.docker import DockerExecResultDTO

        svc.exec_command.return_value = DockerExecResultDTO(
            stdout="out", stderr="", exit_code=0
        )
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/exec",
                    json={"command": "echo hi", "timeout": 30},
                )
        assert resp.status_code == 200
        assert resp.json()["stdout"] == "out"

    async def test_pause_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.pause_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/pause"
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

    async def test_unpause_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.unpause_container.return_value = None
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/unpause"
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "unpaused"

    async def test_stats_success(self) -> None:
        svc = AsyncMock(spec=DockerContainerService)
        svc.get_stats.return_value = _stats_dto(CID)
        app = _create_v2_docker_app(container_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/containers/{CID}/stats"
                )
        assert resp.status_code == 200
        assert resp.json()["Container"] == CID


# ---------------------------------------------------------------------------
# Images single endpoints
# ---------------------------------------------------------------------------


class TestImagesSingle:
    async def test_pull_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.pull_image.return_value = _pull_dto(IMG, True)
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/pull",
                    json={"image": IMG},
                )
        assert resp.status_code == 200
        assert resp.json()["image"] == IMG

    async def test_build_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        from app.application.dto.docker import DockerImageBuildResultDTO

        svc.build_image.return_value = DockerImageBuildResultDTO(
            image_id="sha256:abc", tag="myimg:1", output="built"
        )
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/build",
                    json={
                        "dockerfile": "FROM alpine",
                        "tag": "myimg:1",
                        "build_args": {"A": "b"},
                        "no_cache": True,
                    },
                )
        assert resp.status_code == 200
        assert resp.json()["image_id"] == "sha256:abc"

    async def test_history_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.image_history.return_value = [
            {
                "ID": "layer1",
                "CreatedAt": "2026-01-01",
                "CreatedBy": "/bin/sh",
                "Size": "10MB",
                "Comment": "",
            }
        ]
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/{IMG}/history"
                )
        assert resp.status_code == 200
        assert len(resp.json()["layers"]) == 1
        assert resp.json()["layers"][0]["id"] == "layer1"

    async def test_tag_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        from app.application.dto.docker import DockerImageTagResultDTO

        svc.tag_image.return_value = DockerImageTagResultDTO(
            source=IMG, target="myrepo:tag"
        )
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/{IMG}/tag",
                    json={"repo": "myrepo", "tag": "tag"},
                )
        assert resp.status_code == 200
        assert resp.json()["target"] == "myrepo:tag"

    async def test_push_path_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.push_image.return_value = _pull_dto(IMG, True)
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/{IMG}/push"
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_inspect_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        from app.application.dto.docker import DockerImageInspectDTO

        svc.inspect_image.return_value = DockerImageInspectDTO(
            id="sha256:abc",
            repo_tags=("alpine:latest",),
            size=100,
            created="2026-01-01",
            architecture="amd64",
            os="linux",
        )
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/images/{IMG}")
        assert resp.status_code == 200
        assert resp.json()["id"] == "sha256:abc"

    async def test_remove_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.remove_image.return_value = None
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/nodes/{NODE_ID}/docker/images/{IMG}")
        assert resp.status_code == 204

    async def test_push_body_success(self) -> None:
        svc = AsyncMock(spec=DockerImageService)
        svc.push_image.return_value = _pull_dto(IMG, True)
        app = _create_v2_docker_app(image_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/images/push",
                    json={"image": IMG},
                )
        assert resp.status_code == 200
        assert resp.json()["image"] == IMG


# ---------------------------------------------------------------------------
# Networks / Volumes single
# ---------------------------------------------------------------------------


class TestNetworksSingle:
    async def test_create_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.create_network.return_value = "net123"
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks",
                    json={"name": "mynet", "driver": "bridge"},
                )
        assert resp.status_code == 201
        assert resp.json()["id"] == "net123"

    async def test_inspect_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.inspect_network.return_value = DockerNetworkInspectDTO(
            id=NET,
            name="bridge",
            driver="bridge",
            scope="local",
            subnet="10.0.0.0/24",
            gateway="10.0.0.1",
            containers=(("abc", {"Name": "ctr", "IPv4Address": "10.0.0.2"}),),
        )
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/networks/{NET}")
        assert resp.status_code == 200
        assert resp.json()["id"] == NET

    async def test_remove_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_network.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/nodes/{NODE_ID}/docker/networks/{NET}")
        assert resp.status_code == 204

    async def test_connect_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.connect_to_network.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks/{NET}/connect",
                    json={"container_id": CID},
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"

    async def test_disconnect_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.disconnect_from_network.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/networks/{NET}/disconnect",
                    json={"container_id": CID, "force": True},
                )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disconnected"

    async def test_inspect_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/networks/{BAD_ID}")
        assert resp.status_code == 422


class TestVolumesSingle:
    async def test_create_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.create_volume.return_value = VOL
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v2/nodes/{NODE_ID}/docker/volumes",
                    json={"name": VOL},
                )
        assert resp.status_code == 201
        assert resp.json()["name"] == VOL

    async def test_inspect_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.inspect_volume.return_value = DockerVolumeInspectDTO(
            name=VOL,
            driver="local",
            mountpoint="/var/lib/docker",
            labels=(("a", "b"),),
        )
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/volumes/{VOL}")
        assert resp.status_code == 200
        assert resp.json()["name"] == VOL

    async def test_remove_success(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        svc.remove_volume.return_value = None
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/nodes/{NODE_ID}/docker/volumes/{VOL}")
        assert resp.status_code == 204

    async def test_inspect_invalid_422(self) -> None:
        svc = AsyncMock(spec=DockerResourceService)
        app = _create_v2_docker_app(resource_service=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{NODE_ID}/docker/volumes/{BAD_ID}")
        assert resp.status_code == 422
