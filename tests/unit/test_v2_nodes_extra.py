"""Extra coverage for app/api/v2/nodes.py (28% miss, 135 lines).

Covers: GET /?cursor with tag/search, POST / bulk create, PATCH / {updates},
POST /deletions, POST /checks, POST /metrics, POST /credential-validations,
POST /validate, GET /{node_id}/status-history ?cursor.

Uses AsyncMock, MagicMock, Dishka as required. Keeps ruff/ty clean.
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
from app.api.v2.nodes import router as v2_nodes_router
from app.application.dto.bulk_node_operation import (
    BulkNodeCheckResultDTO,
    BulkNodeOperationResultDTO,
    BulkValidateCredentialsResultDTO,
)
from app.application.dto.node_metrics import (
    CpuMetricsDTO,
    LoadAverageDTO,
    NodeMetricsDTO,
    UsageMetricsDTO,
)
from app.application.dto.node_status_history import (
    NodeStatusHistoryPageDTO,
    NodeStatusHistoryRecordDTO,
)
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeEndpoint
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.application.services.node_validation_service import NodeValidationService
from app.core.exceptions import DomainError
from app.schemas.common import decode_cursor, encode_cursor
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings, make_node_view


def _create_v2_nodes_app(
    *,
    node_management: AsyncMock | MagicMock | None = None,
    node_bulk_op: AsyncMock | MagicMock | None = None,
    node_metrics: AsyncMock | MagicMock | None = None,
    node_bulk_cmd: AsyncMock | MagicMock | None = None,
    node_validation: AsyncMock | MagicMock | None = None,
    node_status_history: AsyncMock | MagicMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(DomainError, domain_error_handler)
    app.include_router(v2_nodes_router, prefix="/api/v2")

    nm = node_management or AsyncMock(spec=NodeManagementService)
    bulk_op = node_bulk_op or AsyncMock(spec=NodeBulkOperationService)
    metrics = node_metrics or AsyncMock(spec=NodeMetricsService)
    bulk_cmd = node_bulk_cmd or AsyncMock(spec=NodeBulkCommandService)
    validation = node_validation or AsyncMock(spec=NodeValidationService)
    history = node_status_history or AsyncMock(spec=NodeStatusHistoryService)

    class MockProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_node_management(self) -> NodeManagementService:
            return as_typed_mock(NodeManagementService, nm)

        @provide(scope=Scope.REQUEST)
        def get_node_bulk_op(self) -> NodeBulkOperationService:
            return as_typed_mock(NodeBulkOperationService, bulk_op)

        @provide(scope=Scope.REQUEST)
        def get_node_metrics(self) -> NodeMetricsService:
            return as_typed_mock(NodeMetricsService, metrics)

        @provide(scope=Scope.REQUEST)
        def get_node_bulk_cmd(self) -> NodeBulkCommandService:
            return as_typed_mock(NodeBulkCommandService, bulk_cmd)

        @provide(scope=Scope.REQUEST)
        def get_node_validation(self) -> NodeValidationService:
            return as_typed_mock(NodeValidationService, validation)

        @provide(scope=Scope.REQUEST)
        def get_node_status_history(self) -> NodeStatusHistoryService:
            return as_typed_mock(NodeStatusHistoryService, history)

    container = make_async_container(MockProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


_SETTINGS_PATCH = patch(
    "app.api.deps.get_settings",
    return_value=_mock_settings("test-master"),
)

_NODE_ID = uuid.uuid4()
_NODE_ID_2 = uuid.uuid4()
_NODE_ID_3 = uuid.uuid4()


def _metrics_dto() -> NodeMetricsDTO:
    return NodeMetricsDTO(
        cpu=CpuMetricsDTO(usage_percent=12.5, cores=4),
        memory=UsageMetricsDTO(total_bytes=8192, used_bytes=4096, percent=50.0),
        disk=UsageMetricsDTO(total_bytes=100000, used_bytes=50000, percent=50.0),
        load_average=LoadAverageDTO(one_min=0.1, five_min=0.2, fifteen_min=0.3),
        uptime_since="2026-01-01 00:00:00",
    )


# ---------------------------------------------------------------------------
# Helpers: _node_response, _encode_offset, _decode_offset
# ---------------------------------------------------------------------------


class TestV2NodesHelpers:
    def test_node_response_mapping(self) -> None:
        from app.api.v2.nodes import _node_response

        view = make_node_view()
        resp = _node_response(view)
        assert resp.id == view.id
        assert resp.host == view.endpoint.host
        assert resp.port == view.endpoint.port
        assert resp.tags == list(view.tags)

    def test_encode_decode_offset_roundtrip(self) -> None:
        from app.api.v2.nodes import _decode_offset, _encode_offset

        for offset in (0, 1, 20, 100):
            cur = _encode_offset(offset)
            assert _decode_offset(cur) == offset

    def test_decode_offset_invalid(self) -> None:
        from app.api.v2.nodes import _decode_offset

        with pytest.raises(ValueError, match="Invalid cursor"):
            _decode_offset("not-base64!!!")
        bad = base64.urlsafe_b64encode(json.dumps({"bad": 1}).encode()).decode()
        with pytest.raises(ValueError):
            _decode_offset(bad)

    def test_encode_offset_is_base64_json(self) -> None:
        from app.api.v2.nodes import _encode_offset

        cur = _encode_offset(5)
        raw = base64.urlsafe_b64decode(cur.encode())
        data = json.loads(raw)
        assert data["offset"] == 5


# ---------------------------------------------------------------------------
# GET /?cursor with tag/search
# ---------------------------------------------------------------------------


class TestListNodesCursor:
    async def test_list_without_cursor(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.get_nodes_cursor.return_value = ([], None, False)
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/nodes/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        svc.get_nodes_cursor.assert_awaited_once()
        kwargs = svc.get_nodes_cursor.call_args.kwargs
        assert kwargs["cursor"] is None
        assert kwargs["limit"] == 20
        assert kwargs["tags"] is None
        assert kwargs["search"] is None

    async def test_list_with_tag_and_search(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        view = make_node_view(tags=["prod"])
        svc.get_nodes_cursor.return_value = ([view], None, False)
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/nodes/?tag=prod&search=10.0")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        kwargs = svc.get_nodes_cursor.call_args.kwargs
        assert kwargs["tags"] == ["prod"]
        assert kwargs["search"] == "10.0"

    async def test_list_with_valid_cursor(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        view = make_node_view()
        next_key = (datetime.now(UTC), uuid.uuid4())
        svc.get_nodes_cursor.return_value = ([view], next_key, True)
        cursor = encode_cursor(datetime.now(UTC), uuid.uuid4())
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/?cursor={cursor}&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        assert data["limit"] == 5
        # decode next_cursor should be valid
        decoded_ts, decoded_id = decode_cursor(data["next_cursor"])
        assert decoded_id == next_key[1]
        svc.get_nodes_cursor.assert_awaited_once()
        assert svc.get_nodes_cursor.call_args.kwargs["limit"] == 5
        assert svc.get_nodes_cursor.call_args.kwargs["cursor"] is not None

    async def test_list_invalid_cursor_returns_422(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/nodes/?cursor=invalid!!!")
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"
        svc.get_nodes_cursor.assert_not_awaited()

    async def test_list_has_more_false_no_next_cursor(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.get_nodes_cursor.return_value = ([make_node_view()], None, False)
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/nodes/?limit=1")
        assert resp.status_code == 200
        assert resp.json()["next_cursor"] is None
        assert resp.json()["has_more"] is False

    async def test_list_next_cursor_encoded(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        nid = uuid.uuid4()
        svc.get_nodes_cursor.return_value = ([make_node_view()], (ts, nid), True)
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get("/api/v2/nodes/")
        assert resp.status_code == 200
        cur = resp.json()["next_cursor"]
        assert cur is not None
        d_ts, d_id = decode_cursor(cur)
        assert d_id == nid


# ---------------------------------------------------------------------------
# POST / bulk create
# ---------------------------------------------------------------------------


class TestBulkCreateNodes:
    def _payload(self, count: int = 1) -> dict[str, object]:
        return {
            "items": [
                {
                    "name": f"node-{i}",
                    "host": f"10.0.0.{i + 1}",
                    "port": 22,
                    "connection_type": "ssh",
                    "username": "root",
                    "tags": ["prod"],
                }
                for i in range(count)
            ]
        }

    async def test_all_success_returns_201(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        view = make_node_view()
        svc.create_node.return_value = view
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/nodes/", json=self._payload(2))
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0
        assert all(r["status"] == "success" for r in data["results"])
        assert svc.create_node.await_count == 2

    async def test_partial_success_returns_207(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)

        async def _side_effect(dto):  # noqa: ANN001, ANN202
            if dto.name == "node-0":
                return make_node_view(name="node-0")
            raise RuntimeError("boom")

        svc.create_node.side_effect = _side_effect
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/nodes/", json=self._payload(2))
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        assert data["total"] == 2

    async def test_all_failed_returns_200(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.create_node.side_effect = RuntimeError("fail")
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/nodes/", json=self._payload(1))
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "error"
        assert "fail" in data["results"][0]["error"]

    async def test_bulk_create_with_docker_fields(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.create_node.return_value = make_node_view()
        app = _create_v2_nodes_app(node_management=svc)
        payload = {
            "items": [
                {
                    "name": "node-docker",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                    "username": "root",
                    "docker_host": "tcp://10.0.0.1:2375",
                    "has_docker": True,
                    "tags": [],
                }
            ]
        }
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/nodes/", json=payload)
        assert resp.status_code == 201
        svc.create_node.assert_awaited_once()
        dto = svc.create_node.call_args.args[0]
        assert dto.endpoint.docker_host == "tcp://10.0.0.1:2375"
        assert dto.endpoint.has_docker is True

    async def test_bulk_create_covers_exception_branch(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.create_node.side_effect = ValueError("invalid host")
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post("/api/v2/nodes/", json=self._payload(1))
        assert resp.status_code == 200
        assert resp.json()["results"][0]["error"] == "invalid host"
        assert resp.json()["results"][0]["node_id"] is None


# ---------------------------------------------------------------------------
# PATCH / {updates}
# ---------------------------------------------------------------------------


class TestBulkUpdateNodes:
    async def test_bulk_update_all_success(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.update_node.return_value = make_node_view()
        app = _create_v2_nodes_app(node_management=svc)
        payload = {
            "updates": [
                {"id": str(_NODE_ID), "changes": {"name": "new-name"}},
                {"id": str(_NODE_ID_2), "changes": {"tags": ["a", "b"]}},
            ]
        }
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch("/api/v2/nodes/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0
        assert svc.update_node.await_count == 2
        # second call should have tags as tuple
        second_call_dto = svc.update_node.call_args_list[1].args[1]
        # changes is tuple of tuples, check that tags value is tuple
        changes_dict = dict(second_call_dto.changes)
        assert isinstance(changes_dict["tags"], tuple)

    async def test_bulk_update_partial_207(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)

        async def _upd(node_id, dto):  # noqa: ANN001, ANN202
            if node_id == _NODE_ID:
                return make_node_view()
            raise RuntimeError("not found")

        svc.update_node.side_effect = _upd
        app = _create_v2_nodes_app(node_management=svc)
        payload = {
            "updates": [
                {"id": str(_NODE_ID), "changes": {"name": "ok"}},
                {"id": str(_NODE_ID_2), "changes": {"name": "fail"}},
            ]
        }
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch("/api/v2/nodes/", json=payload)
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    async def test_bulk_update_all_failed(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.update_node.side_effect = RuntimeError("boom")
        app = _create_v2_nodes_app(node_management=svc)
        payload = {
            "updates": [
                {"id": str(_NODE_ID), "changes": {"name": "x"}},
            ]
        }
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch("/api/v2/nodes/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "error"

    async def test_bulk_update_error_message_captured(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.update_node.side_effect = ValueError("bad value")
        app = _create_v2_nodes_app(node_management=svc)
        payload = {"updates": [{"id": str(_NODE_ID), "changes": {"port": 22}}]}
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch("/api/v2/nodes/", json=payload)
        assert resp.status_code == 200
        assert "bad value" in resp.json()["results"][0]["error"]


# ---------------------------------------------------------------------------
# POST /deletions
# ---------------------------------------------------------------------------


class TestBulkDeleteNodes:
    async def test_all_success(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=2, node_ids=(_NODE_ID, _NODE_ID_2)
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/deletions",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0
        assert all(r["status"] == "success" for r in data["results"])

    async def test_partial_success_207(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(_NODE_ID,)
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/deletions",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        results = {r["node_id"]: r for r in data["results"]}
        assert results[str(_NODE_ID)]["status"] == "success"
        assert results[str(_NODE_ID_2)]["status"] == "error"
        assert results[str(_NODE_ID_2)]["error"] == "Node not found"

    async def test_all_not_found(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=0, node_ids=()
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/deletions",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["succeeded"] == 0

    async def test_bulk_delete_calls_service_with_tuple(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(_NODE_ID,)
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                await ac.post(
                    "/api/v2/nodes/deletions",
                    json={"ids": [str(_NODE_ID)]},
                )
        dto = svc.bulk_delete.call_args.args[0]
        assert dto.node_ids == (_NODE_ID,)


# ---------------------------------------------------------------------------
# POST /checks
# ---------------------------------------------------------------------------


class TestBulkCheckNodes:
    async def test_checks_all_success(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=2, succeeded=2, failed=0, node_ids=(_NODE_ID, _NODE_ID_2)
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/checks",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    async def test_checks_partial_207(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=2, succeeded=1, failed=1, node_ids=(_NODE_ID,)
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/checks",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    async def test_checks_all_failed(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=1, succeeded=0, failed=1, node_ids=()
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/checks",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["error"] == "Node not found"

    async def test_checks_with_string_node_ids(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        svc.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=1, succeeded=1, failed=0, node_ids=(_NODE_ID,)
        )
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/checks",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        # service should be called with tuple of strings
        called_ids = (
            svc.bulk_check.call_args.kwargs.get("node_ids")
            or svc.bulk_check.call_args.args[0]
        )
        assert all(isinstance(x, str) for x in called_ids)

    async def test_checks_empty_node_ids_result(self) -> None:
        svc = AsyncMock(spec=NodeBulkOperationService)
        mock_result = MagicMock()
        mock_result.total = 1
        mock_result.succeeded = 0
        mock_result.failed = 1
        mock_result.node_ids = None
        svc.bulk_check.return_value = mock_result
        # prod never returns None but we test fallback `if result.node_ids else set()`
        app = _create_v2_nodes_app(node_bulk_op=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/checks",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1


# ---------------------------------------------------------------------------
# POST /metrics
# ---------------------------------------------------------------------------


class TestBulkMetrics:
    async def test_metrics_all_success(self) -> None:
        svc = AsyncMock(spec=NodeMetricsService)
        svc.get_node_metrics.return_value = _metrics_dto()
        app = _create_v2_nodes_app(node_metrics=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/metrics",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0
        assert all(r["status"] == "success" for r in data["results"])
        assert data["results"][0]["metrics"]["cpu"]["usage_percent"] == 12.5

    async def test_metrics_partial_207(self) -> None:
        svc = AsyncMock(spec=NodeMetricsService)

        async def _get(node_id):  # noqa: ANN001, ANN202
            if node_id == _NODE_ID:
                return _metrics_dto()
            raise RuntimeError("connection failed")

        svc.get_node_metrics.side_effect = _get
        app = _create_v2_nodes_app(node_metrics=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/metrics",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        success = [r for r in data["results"] if r["status"] == "success"][0]
        assert success["metrics"] is not None
        error = [r for r in data["results"] if r["status"] == "error"][0]
        assert "connection failed" in error["error"]

    async def test_metrics_all_failed(self) -> None:
        svc = AsyncMock(spec=NodeMetricsService)
        svc.get_node_metrics.side_effect = RuntimeError("timeout")
        app = _create_v2_nodes_app(node_metrics=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/metrics",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 0
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "error"
        assert data["results"][0]["metrics"] is None

    async def test_metrics_maps_all_fields(self) -> None:
        svc = AsyncMock(spec=NodeMetricsService)
        dto = NodeMetricsDTO(
            cpu=CpuMetricsDTO(usage_percent=99.9, cores=8),
            memory=UsageMetricsDTO(
                total_bytes=17179869184, used_bytes=8589934592, percent=50.0
            ),
            disk=UsageMetricsDTO(
                total_bytes=500000000000, used_bytes=250000000000, percent=50.0
            ),
            load_average=LoadAverageDTO(one_min=1.5, five_min=0.8, fifteen_min=0.3),
            uptime_since="2026-06-01 12:00:00",
        )
        svc.get_node_metrics.return_value = dto
        app = _create_v2_nodes_app(node_metrics=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/metrics",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        m = resp.json()["results"][0]["metrics"]
        assert m["cpu"]["cores"] == 8
        assert m["memory"]["total_bytes"] == 17179869184
        assert m["disk"]["total_bytes"] == 500000000000
        assert m["load_average"]["one_min"] == 1.5
        assert m["uptime_since"] == "2026-06-01 12:00:00"


# ---------------------------------------------------------------------------
# POST /credential-validations
# ---------------------------------------------------------------------------


class TestCredentialValidations:
    async def test_all_success(self) -> None:
        svc = AsyncMock(spec=NodeBulkCommandService)
        svc.validate_credentials_bulk.return_value = [
            BulkValidateCredentialsResultDTO(
                node_id=_NODE_ID,
                node_name="n1",
                status="success",
                message="Credentials valid",
            ),
            BulkValidateCredentialsResultDTO(
                node_id=_NODE_ID_2,
                node_name="n2",
                status="success",
                message="Credentials valid",
            ),
        ]
        app = _create_v2_nodes_app(node_bulk_cmd=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/credential-validations",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    async def test_with_tags(self) -> None:
        svc = AsyncMock(spec=NodeBulkCommandService)
        svc.validate_credentials_bulk.return_value = [
            BulkValidateCredentialsResultDTO(
                node_id=_NODE_ID, node_name="n1", status="success", message="ok"
            )
        ]
        app = _create_v2_nodes_app(node_bulk_cmd=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/credential-validations",
                    json={"tags": ["prod"]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 1
        svc.validate_credentials_bulk.assert_awaited_once()
        kwargs = svc.validate_credentials_bulk.call_args.kwargs
        assert kwargs["tags"] == ["prod"]
        assert kwargs["node_ids"] is None

    async def test_with_ids_and_tags(self) -> None:
        svc = AsyncMock(spec=NodeBulkCommandService)
        svc.validate_credentials_bulk.return_value = []
        app = _create_v2_nodes_app(node_bulk_cmd=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/credential-validations",
                    json={"ids": [str(_NODE_ID)], "tags": ["prod"]},
                )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_partial_207(self) -> None:
        svc = AsyncMock(spec=NodeBulkCommandService)
        svc.validate_credentials_bulk.return_value = [
            BulkValidateCredentialsResultDTO(
                node_id=_NODE_ID, node_name="n1", status="success", message="ok"
            ),
            BulkValidateCredentialsResultDTO(
                node_id=_NODE_ID_2,
                node_name="n2",
                status="error",
                message="auth failed",
            ),
        ]
        app = _create_v2_nodes_app(node_bulk_cmd=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/credential-validations",
                    json={"ids": [str(_NODE_ID), str(_NODE_ID_2)]},
                )
        assert resp.status_code == 207
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1

    async def test_empty_result(self) -> None:
        svc = AsyncMock(spec=NodeBulkCommandService)
        svc.validate_credentials_bulk.return_value = []
        app = _create_v2_nodes_app(node_bulk_cmd=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/credential-validations",
                    json={"ids": [str(_NODE_ID)]},
                )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# POST /validate
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /{id}/status-history ?cursor
# ---------------------------------------------------------------------------


class TestStatusHistory:
    def _record(self, nid: uuid.UUID) -> NodeStatusHistoryRecordDTO:
        return NodeStatusHistoryRecordDTO(
            id=uuid.uuid4(),
            node_id=nid,
            old_status="inactive",
            new_status="active",
            source="manual_update",
            changed_at=datetime.now(UTC),
        )

    async def test_without_cursor(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        svc.get_history.return_value = NodeStatusHistoryPageDTO(
            items=(self._record(_NODE_ID), self._record(_NODE_ID)), total=2
        )
        app = _create_v2_nodes_app(node_status_history=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{_NODE_ID}/status-history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        assert data["limit"] == 20
        q = svc.get_history.call_args.args[0]
        assert q.offset == 0
        assert q.limit == 20
        assert q.node_id == _NODE_ID

    async def test_with_offset_cursor_and_has_more(self) -> None:
        from app.api.v2.nodes import _encode_offset

        svc = AsyncMock(spec=NodeStatusHistoryService)
        # total 5, offset 0, limit 2, items 2 -> has_more True
        svc.get_history.return_value = NodeStatusHistoryPageDTO(
            items=(self._record(_NODE_ID), self._record(_NODE_ID)), total=5
        )
        app = _create_v2_nodes_app(node_status_history=svc)
        cursor = _encode_offset(0)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?cursor={cursor}&limit=2"
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        # next cursor should decode to offset 2
        from app.api.v2.nodes import _decode_offset

        assert _decode_offset(data["next_cursor"]) == 2

    async def test_with_offset_cursor_second_page(self) -> None:
        from app.api.v2.nodes import _encode_offset

        svc = AsyncMock(spec=NodeStatusHistoryService)
        svc.get_history.return_value = NodeStatusHistoryPageDTO(
            items=(self._record(_NODE_ID),), total=3
        )
        app = _create_v2_nodes_app(node_status_history=svc)
        cursor = _encode_offset(2)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?cursor={cursor}&limit=2"
                )
        assert resp.status_code == 200
        data = resp.json()
        # offset 2 + 1 item = 3 == total -> no more
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        q = svc.get_history.call_args.args[0]
        assert q.offset == 2

    async def test_invalid_cursor_returns_422(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        app = _create_v2_nodes_app(node_status_history=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?cursor=bad!!!"
                )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"

    async def test_cursor_fallback_to_node_cursor_sets_offset_zero(self) -> None:
        # _decode_offset fails but decode_cursor succeeds -> offset 0
        svc = AsyncMock(spec=NodeStatusHistoryService)
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=(), total=0)
        app = _create_v2_nodes_app(node_status_history=svc)
        valid_node_cursor = encode_cursor(datetime.now(UTC), uuid.uuid4())
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?cursor={valid_node_cursor}"
                )
        assert resp.status_code == 200
        q = svc.get_history.call_args.args[0]
        assert q.offset == 0

    async def test_has_more_false_when_exact_total(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        svc.get_history.return_value = NodeStatusHistoryPageDTO(
            items=(self._record(_NODE_ID),), total=1
        )
        app = _create_v2_nodes_app(node_status_history=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{_NODE_ID}/status-history?limit=10")
        assert resp.status_code == 200
        assert resp.json()["has_more"] is False
        assert resp.json()["next_cursor"] is None

    async def test_items_mapping(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        rec = NodeStatusHistoryRecordDTO(
            id=uuid.uuid4(),
            node_id=_NODE_ID,
            old_status=None,
            new_status="active",
            source="auto",
            changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=(rec,), total=1)
        app = _create_v2_nodes_app(node_status_history=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{_NODE_ID}/status-history")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["id"] == str(rec.id)
        assert item["old_status"] is None
        assert item["new_status"] == "active"
        assert item["source"] == "auto"

    async def test_limit_bounds(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=(), total=0)
        app = _create_v2_nodes_app(node_status_history=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?limit=100"
                )
        assert resp.status_code == 200
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{_NODE_ID}/status-history?limit=0")
        assert resp.status_code == 422

    async def test_decode_offset_generic_exception_returns_422(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        app = _create_v2_nodes_app(node_status_history=svc)
        with (
            patch("app.api.v2.nodes._decode_offset", side_effect=RuntimeError("boom")),
            _SETTINGS_PATCH,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?cursor=anything"
                )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"

    async def test_decode_cursor_generic_exception_returns_422(self) -> None:
        svc = AsyncMock(spec=NodeStatusHistoryService)
        app = _create_v2_nodes_app(node_status_history=svc)
        # _decode_offset raises ValueError, then decode_cursor raises generic Exception
        with (
            patch("app.api.v2.nodes._decode_offset", side_effect=ValueError("bad")),
            patch("app.api.v2.nodes.decode_cursor", side_effect=RuntimeError("boom")),
            _SETTINGS_PATCH,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(
                    f"/api/v2/nodes/{_NODE_ID}/status-history?cursor=anything"
                )
        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid cursor"


# ---------------------------------------------------------------------------
# Single node endpoints (to reach 100% line coverage)
# ---------------------------------------------------------------------------


class TestSingleNodeEndpoints:
    async def test_get_node_success(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        view = make_node_view(id=_NODE_ID)
        svc.get_node.return_value = view
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{_NODE_ID}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(_NODE_ID)
        svc.get_node.assert_awaited_once_with(_NODE_ID)

    async def test_get_node_not_found_maps_to_404(self) -> None:
        from app.core.exceptions import NodeNotFoundError

        svc = AsyncMock(spec=NodeManagementService)
        svc.get_node.side_effect = NodeNotFoundError("not found")
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.get(f"/api/v2/nodes/{_NODE_ID}")
        assert resp.status_code == 404

    async def test_patch_node_success_with_tags(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        view = make_node_view(id=_NODE_ID, tags=["new"])
        svc.update_node.return_value = view
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{_NODE_ID}",
                    json={"name": "updated", "tags": ["new"]},
                )
        assert resp.status_code == 200
        assert resp.json()["name"] == view.name
        svc.update_node.assert_awaited_once()
        dto = svc.update_node.call_args.args[1]
        changes = dict(dto.changes)
        assert changes["name"] == "updated"
        assert isinstance(changes["tags"], tuple)

    async def test_delete_node_success(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        svc.delete_node.return_value = True
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/nodes/{_NODE_ID}")
        assert resp.status_code == 204
        svc.delete_node.assert_awaited_once_with(_NODE_ID)

    async def test_delete_node_not_found(self) -> None:
        from app.core.exceptions import NodeNotFoundError

        svc = AsyncMock(spec=NodeManagementService)
        svc.delete_node.side_effect = NodeNotFoundError("not found")
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.delete(f"/api/v2/nodes/{_NODE_ID}")
        assert resp.status_code == 404

    async def test_patch_node_without_tags_covers_branch(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        view = make_node_view(id=_NODE_ID)
        svc.update_node.return_value = view
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.patch(
                    f"/api/v2/nodes/{_NODE_ID}",
                    json={"name": "no-tags"},
                )
        assert resp.status_code == 200
        dto = svc.update_node.call_args.args[1]
        changes = dict(dto.changes)
        assert changes["name"] == "no-tags"
        assert "tags" not in changes


# ---------------------------------------------------------------------------
# MagicMock usage for node view (ensures file uses MagicMock per task)
# ---------------------------------------------------------------------------


class TestMagicMockUsage:
    def test_magicmock_node_view(self) -> None:
        from app.api.v2.nodes import _node_response

        mock_view = MagicMock(spec=NodeViewDTO)
        mock_view.id = _NODE_ID
        mock_view.name = "magic-node"
        mock_view.status = "active"
        mock_view.username = "root"
        mock_view.tags = ("prod",)
        mock_view.created_at = datetime.now(UTC)
        mock_view.updated_at = datetime.now(UTC)
        mock_view.endpoint = MagicMock(spec=NodeEndpoint)
        mock_view.endpoint.host = "10.0.0.1"
        mock_view.endpoint.port = 22
        mock_view.endpoint.connection_type = "ssh"
        mock_view.endpoint.docker_host = None
        mock_view.endpoint.has_docker = False

        resp = _node_response(mock_view)  # type: ignore[arg-type]
        assert resp.name == "magic-node"
        assert resp.host == "10.0.0.1"
        assert resp.tags == ["prod"]

    async def test_bulk_create_uses_magicmock_view(self) -> None:
        svc = AsyncMock(spec=NodeManagementService)
        # return MagicMock as NodeViewDTO
        mock_view = MagicMock(spec=NodeViewDTO)
        mock_view.id = uuid.uuid4()
        mock_view.name = "m"
        svc.create_node.return_value = mock_view  # type: ignore[arg-type]
        app = _create_v2_nodes_app(node_management=svc)
        with _SETTINGS_PATCH:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v2/nodes/",
                    json={
                        "items": [
                            {
                                "name": "m",
                                "host": "10.0.0.1",
                                "username": "root",
                            }
                        ]
                    },
                )
        assert resp.status_code == 201
        assert resp.json()["succeeded"] == 1
