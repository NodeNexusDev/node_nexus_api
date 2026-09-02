"""Coverage for app/api/v2/audit.py — pagination, exports, stats, delete, get."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v2 import audit as audit_module
from app.api.v2.audit import _decode_offset, _encode_offset, _to_response, router
from app.application.dto.audit import AuditLogDTO, AuditLogPageDTO
from app.application.dto.export import AuditExportRowDTO
from app.application.ports.export import AuditExporter
from app.application.services.audit_log_service import AuditLogService
from app.schemas.common import BulkResult
from tests.typing import as_typed_mock
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _make_audit_dto(**overrides: Any) -> AuditLogDTO:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "action": "create",
        "user": "tester",
        "details": "detail",
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return AuditLogDTO(**defaults)  # type: ignore[arg-type]


def _make_row(**overrides: Any) -> AuditExportRowDTO:
    defaults: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "action": "create",
        "node_id": str(uuid.uuid4()),
        "user": "tester",
        "details": "{}",
        "created_at": datetime.now(UTC).isoformat(),
    }
    defaults.update(overrides)
    return AuditExportRowDTO(**defaults)  # type: ignore[arg-type]


def _create_audit_app(
    service_mock: AsyncMock | MagicMock | None = None,
    exporter_mock: AsyncMock | MagicMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v2")

    svc = service_mock if service_mock is not None else AsyncMock()
    exp = exporter_mock if exporter_mock is not None else AsyncMock()

    class AuditTestProvider(Provider):
        @provide(scope=Scope.APP)
        def get_service(self) -> AuditLogService:
            return as_typed_mock(AuditLogService, svc)

        @provide(scope=Scope.REQUEST)
        def get_exporter(self) -> AuditExporter:
            return as_typed_mock(AuditExporter, exp)

    container = make_async_container(AuditTestProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


# ---------------------------------------------------------------------------
# Helpers: _encode_offset / _decode_offset / _to_response
# ---------------------------------------------------------------------------


class TestAuditHelpers:
    def test_encode_decode_roundtrip(self) -> None:
        for offset in [0, 1, 20, 100]:
            cur = _encode_offset(offset)
            assert _decode_offset(cur) == offset

    def test_decode_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid cursor"):
            _decode_offset("not-base64!!!")

        with pytest.raises(ValueError, match="Invalid cursor"):
            bad = base64.urlsafe_b64encode(b'{"missing":123}').decode()
            _decode_offset(bad)

        with pytest.raises(ValueError, match="Invalid cursor"):
            bad2 = base64.urlsafe_b64encode(b"not-json").decode()
            _decode_offset(bad2)

    def test_to_response_maps(self) -> None:
        dto = _make_audit_dto()
        resp = _to_response(dto)
        assert resp.id == dto.id
        assert resp.action == dto.action
        assert resp.user == dto.user

    def test_encode_is_base64_json(self) -> None:
        cur = _encode_offset(42)
        raw = base64.urlsafe_b64decode(cur.encode())
        data = json.loads(raw)
        assert data["offset"] == 42


# ---------------------------------------------------------------------------
# List GET /?cursor&limit&filters
# ---------------------------------------------------------------------------


class TestListAuditLogs:
    async def test_list_default_pagination(self) -> None:
        svc = AsyncMock()
        svc.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        assert data["limit"] == 20
        svc.get_logs.assert_awaited_once()
        kwargs = svc.get_logs.call_args.kwargs
        assert kwargs["page"] == 1
        assert kwargs["size"] == 20

    async def test_list_pagination_has_more_and_next_cursor(self) -> None:
        svc = AsyncMock()
        # total 5, limit 2, offset 0 -> has_more True, next_cursor offset 2
        logs = [_make_audit_dto() for _ in range(2)]
        svc.get_logs.return_value = AuditLogPageDTO(items=tuple(logs), total=5)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True
        assert data["next_cursor"] is not None
        # decode next_cursor should be 2
        assert _decode_offset(data["next_cursor"]) == 2

    async def test_list_pagination_second_page_via_cursor(self) -> None:
        svc = AsyncMock()
        # First page offset 2, limit 2, total 3 -> one item left, has_more False after?
        # offset 2 + 1 item = 3 total -> has_more False
        log_one = _make_audit_dto()
        svc.get_logs.return_value = AuditLogPageDTO(items=(log_one,), total=3)
        cursor = _encode_offset(2)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/?cursor={cursor}&limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        # service should have been called with page = offset//limit+1 =2//2+1=2
        kwargs = svc.get_logs.call_args.kwargs
        assert kwargs["page"] == 2
        assert kwargs["size"] == 2

    async def test_list_pagination_no_more_when_exact(self) -> None:
        svc = AsyncMock()
        logs = [_make_audit_dto() for _ in range(2)]
        svc.get_logs.return_value = AuditLogPageDTO(items=tuple(logs), total=2)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/?limit=2")
        assert resp.status_code == 200
        assert resp.json()["has_more"] is False
        assert resp.json()["next_cursor"] is None

    async def test_list_invalid_cursor_422(self) -> None:
        svc = AsyncMock()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/?cursor=invalid!!!")
        assert resp.status_code == 422
        assert "Invalid cursor" in resp.json()["detail"]
        svc.get_logs.assert_not_awaited()

    async def test_list_filters_all(self) -> None:
        svc = AsyncMock()
        svc.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        nid = uuid.uuid4()
        dt_from = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
        dt_to = datetime(2026, 1, 31, tzinfo=UTC).isoformat()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(
                    "/api/v2/audit/",
                    params={
                        "node_id": str(nid),
                        "action": "create",
                        "user": "alice",
                        "date_from": dt_from,
                        "date_to": dt_to,
                        "limit": 5,
                    },
                )
        assert resp.status_code == 200
        kwargs = svc.get_logs.call_args.kwargs
        assert kwargs["node_id"] == nid
        assert kwargs["action"] == "create"
        assert kwargs["user"] == "alice"
        assert kwargs["date_from"] is not None
        assert kwargs["date_to"] is not None
        assert kwargs["page"] == 1
        assert kwargs["size"] == 5

    async def test_list_filters_individually(self) -> None:
        for qs, expected in [
            ("node_id", "node_id"),
            ("action", "action"),
            ("user", "user"),
        ]:
            svc = AsyncMock()
            svc.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
            app = _create_audit_app(service_mock=svc)
            nid = uuid.uuid4()
            url = "/api/v2/audit/?limit=10"
            if qs == "node_id":
                url = f"/api/v2/audit/?node_id={nid}"
            elif qs == "action":
                url = "/api/v2/audit/?action=delete"
            elif qs == "user":
                url = "/api/v2/audit/?user=bob"
            with patch(
                "app.api.deps.get_settings",
                return_value=_mock_settings("test-master"),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-master"},
                ) as client:
                    resp = await client.get(url)
            assert resp.status_code == 200, url
            assert svc.get_logs.call_args.kwargs[expected] is not None

    async def test_list_with_cursor_filters(self) -> None:
        svc = AsyncMock()
        svc.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        nid = uuid.uuid4()
        cursor = _encode_offset(10)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(
                    f"/api/v2/audit/?cursor={cursor}&limit=10&node_id={nid}&action=check&user=joe"
                )
        assert resp.status_code == 200
        # offset 10, limit 10 => page 2
        assert svc.get_logs.call_args.kwargs["page"] == 2


# ---------------------------------------------------------------------------
# DELETE /?confirm master only
# ---------------------------------------------------------------------------


class TestDeleteAuditLogs:
    async def test_delete_master_success(self) -> None:
        svc = AsyncMock()
        svc.delete_all_logs.return_value = 5
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.delete("/api/v2/audit/?confirm=yes")
        assert resp.status_code == 204
        svc.delete_all_logs.assert_awaited_once()

    async def test_delete_non_master_403(self) -> None:
        svc = AsyncMock()
        app = _create_audit_app(service_mock=svc)
        # request with non-master key, but settings master is test-master
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "not-master-key"},
            ) as client:
                resp = await client.delete("/api/v2/audit/?confirm=yes")
        assert resp.status_code == 403
        assert "master" in resp.json()["detail"].lower()
        svc.delete_all_logs.assert_not_awaited()

    async def test_delete_missing_confirm_422(self) -> None:
        svc = AsyncMock()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.delete("/api/v2/audit/")
        assert resp.status_code == 422
        assert "confirm=yes" in resp.json()["detail"]
        svc.delete_all_logs.assert_not_awaited()

    async def test_delete_wrong_confirm_422(self) -> None:
        svc = AsyncMock()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.delete("/api/v2/audit/?confirm=no")
        assert resp.status_code == 422
        svc.delete_all_logs.assert_not_awaited()

    async def test_delete_requires_auth_401(self) -> None:
        svc = AsyncMock()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.delete("/api/v2/audit/?confirm=yes")
        assert resp.status_code == 401

    async def test_delete_master_but_no_confirm_then_no_call(self) -> None:
        # also cover delete_audit_logs lines 128-138 fully
        svc = AsyncMock()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.delete("/api/v2/audit/?confirm=maybe")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Exports GET /exports fmt csv/json
# ---------------------------------------------------------------------------


class TestExportAudit:
    async def test_export_csv_default(self) -> None:
        rows = [_make_row(), _make_row()]
        exp = AsyncMock()
        exp.export_audit.return_value = rows
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/exports")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        # CSV should contain header
        assert "id,action,node_id" in resp.text
        exp.export_audit.assert_awaited_once()
        # fmt default csv -> query fmt csv
        q = exp.export_audit.call_args.args[0]
        assert q.fmt == "csv"

    async def test_export_csv_explicit(self) -> None:
        rows = [_make_row()]
        exp = AsyncMock()
        exp.export_audit.return_value = rows
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/exports?fmt=csv&limit=10")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    async def test_export_json(self) -> None:
        rows = [_make_row(id="abc"), _make_row(id="def")]
        exp = AsyncMock()
        exp.export_audit.return_value = rows
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/exports?fmt=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = json.loads(resp.text)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["id"] == "abc"

    async def test_export_json_empty(self) -> None:
        exp = AsyncMock()
        exp.export_audit.return_value = []
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/exports?fmt=json")
        assert resp.status_code == 200
        assert json.loads(resp.text) == []

    async def test_export_csv_empty(self) -> None:
        exp = AsyncMock()
        exp.export_audit.return_value = []
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/exports?fmt=csv")
        assert resp.status_code == 200
        # rows_to_csv([]) returns ""
        assert resp.text == ""

    async def test_export_pagination_csv(self) -> None:
        rows = [_make_row(id=str(i)) for i in range(5)]
        exp = AsyncMock()
        exp.export_audit.return_value = rows
        cursor = _encode_offset(1)
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                url = f"/api/v2/audit/exports?fmt=csv&cursor={cursor}&limit=2"
                resp = await client.get(url)
        assert resp.status_code == 200
        # sliced rows[1:3] => 2 rows plus header = 3 lines
        lines = [line for line in resp.text.strip().splitlines() if line]
        assert len(lines) == 3  # header + 2 rows
        assert "1" in lines[1] or "1" in lines[2]

    async def test_export_pagination_json(self) -> None:
        rows = [_make_row(id=str(i)) for i in range(5)]
        exp = AsyncMock()
        exp.export_audit.return_value = rows
        cursor = _encode_offset(2)
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                url = f"/api/v2/audit/exports?fmt=json&cursor={cursor}&limit=2"
                resp = await client.get(url)
        assert resp.status_code == 200
        data = json.loads(resp.text)
        assert len(data) == 2
        assert data[0]["id"] == "2"
        assert data[1]["id"] == "3"

    async def test_export_invalid_cursor_422(self) -> None:
        exp = AsyncMock()
        exp.export_audit.return_value = [_make_row()]
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/exports?cursor=bad!!!")
        assert resp.status_code == 422
        assert "Invalid cursor" in resp.json()["detail"]

    async def test_export_filters(self) -> None:
        exp = AsyncMock()
        exp.export_audit.return_value = []
        nid = uuid.uuid4()
        dt_from = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
        dt_to = datetime(2026, 1, 31, tzinfo=UTC).isoformat()
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(
                    "/api/v2/audit/exports",
                    params={
                        "from_date": dt_from,
                        "to_date": dt_to,
                        "action": "create",
                        "node_id": str(nid),
                        "fmt": "json",
                    },
                )
        assert resp.status_code == 200
        q = exp.export_audit.call_args.args[0]
        assert q.action == "create"
        assert q.node_id == nid
        assert q.fmt == "json"
        assert q.date_from is not None
        assert q.date_to is not None

    async def test_export_all_query_params_pagination(self) -> None:
        # cover limit alias and offset slicing branches
        rows = [_make_row() for _ in range(3)]
        exp = AsyncMock()
        exp.export_audit.return_value = rows
        cursor = _encode_offset(0)
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(
                    f"/api/v2/audit/exports?fmt=csv&cursor={cursor}&limit=1&action=update&node_id={uuid.uuid4()}"
                )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# Stats GET /stats group_by
# ---------------------------------------------------------------------------


class TestAuditStats:
    async def test_stats_aggregate_dict(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(return_value={"total": 5, "buckets": []})
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert data["buckets"] == []
        svc.get_stats.assert_awaited_once()

    async def test_stats_aggregate_dict_with_buckets(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            return_value={
                "total": 2,
                "buckets": [
                    {"bucket": "2026-01-01", "count": 1},
                    {"period": "2026-01-02", "total": 1},
                ],
            }
        )
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["buckets"]) == 2
        assert data["buckets"][0]["bucket"] == "2026-01-01"

    async def test_stats_aggregate_object(self) -> None:
        svc = AsyncMock()

        class Raw:
            total = 3
            buckets = [
                {"bucket": "2026-01-01", "count": 2},
                MagicMock(bucket="2026-01-02", count=1),
            ]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["buckets"]) == 2

    async def test_stats_aggregate_object_buckets_as_objects(self) -> None:
        svc = AsyncMock()

        class BucketObj:
            def __init__(self, b: str, c: int) -> None:
                self.bucket = b
                self.count = c

        class Raw:
            total = 2
            buckets = [BucketObj("2026-01-01", 1), BucketObj("2026-01-02", 1)]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 200
        assert len(resp.json()["buckets"]) == 2

    async def test_stats_aggregate_object_with_period_group(self) -> None:
        svc = AsyncMock()

        class BucketObj:
            period = "2026-01-03"
            total = 7

        class Raw:
            total = 7
            buckets = [BucketObj()]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 200
        # fallback should map period->bucket and total->count
        assert resp.json()["buckets"][0]["bucket"] == "2026-01-03"
        assert resp.json()["buckets"][0]["count"] == 7

    async def test_stats_group_by_day_dict(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            return_value={
                "total": 2,
                "buckets": [
                    {"bucket": "2026-01-01", "count": 1},
                    {"period": "2026-01-02", "total": 1},
                ],
            }
        )
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 200
        data = resp.json()
        # group_by => BulkResult
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2

    async def test_stats_group_by_hour_dict_with_items_key(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            return_value={
                "total": 1,
                "items": [{"bucket": "2026-01-01T10:00", "count": 1}],
            }
        )
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=hour")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    async def test_stats_group_by_week_object(self) -> None:
        svc = AsyncMock()

        class Raw:
            total = 2
            buckets = [{"bucket": "2026-W01", "count": 2}]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=week")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    async def test_stats_group_by_month_object_with_items(self) -> None:
        svc = AsyncMock()

        class BucketObj:
            bucket = "2026-01"
            count = 5

        class Raw:
            total = 5
            items = [BucketObj()]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=month")
        assert resp.status_code == 200
        assert resp.json()["results"][0]["bucket"] == "2026-01"

    async def test_stats_group_by_object_bucket_period_group(self) -> None:
        svc = AsyncMock()

        class BucketObj:
            period = "2026-01-01"
            total = 4

        class Raw:
            total = 4
            buckets = [BucketObj()]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 200
        # bucket should be period
        assert resp.json()["results"][0]["bucket"] == "2026-01-01"
        assert resp.json()["results"][0]["count"] == 4

    async def test_stats_group_by_total_fallback_len(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            return_value={
                "buckets": [
                    {"bucket": "2026-01-01", "count": 1},
                    {"bucket": "2026-01-02", "count": 2},
                ]
            }
        )
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 200
        # total 0 fallback => len(buckets)
        assert resp.json()["total"] == 2

    async def test_stats_with_date_filters(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(return_value={"total": 1, "buckets": []})
        dt_from = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
        dt_to = datetime(2026, 1, 31, tzinfo=UTC).isoformat()
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(
                    "/api/v2/audit/stats",
                    params={"date_from": dt_from, "date_to": dt_to},
                )
        assert resp.status_code == 200
        kwargs = svc.get_stats.call_args.kwargs
        assert kwargs["date_from"] is not None
        assert kwargs["date_to"] is not None

    async def test_stats_attribute_error_500(self) -> None:
        svc = MagicMock()
        # get_stats will raise AttributeError
        svc.get_stats = AsyncMock(side_effect=AttributeError("no get_stats"))
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 500
        assert "not available" in resp.json()["detail"].lower()

    async def test_stats_generic_exception_500(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(side_effect=RuntimeError("boom"))
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 500
        assert "boom" in resp.json()["detail"]

    async def test_stats_aggregate_object_total_as_attr_buckets_dict(self) -> None:
        # covers lines 260-276 with dict buckets and getattr fallback
        svc = AsyncMock()

        class Raw:
            total = 10
            buckets = [{"bucket": "2026-01-01", "count": 10}]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats")
        assert resp.status_code == 200
        assert resp.json()["total"] == 10

    async def test_stats_group_by_object_total_and_buckets_dict(self) -> None:
        # covers lines 298-314 dict branch
        svc = AsyncMock()

        class Raw:
            total = 1
            buckets = [{"bucket": "2026-01-10", "count": 1}]

        svc.get_stats = AsyncMock(return_value=Raw())
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 200
        assert resp.json()["results"][0]["bucket"] == "2026-01-10"

    async def test_stats_bulk_result_type(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            return_value={"total": 1, "buckets": [{"bucket": "b", "count": 1}]}
        )
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 200
        validated = BulkResult.model_validate(resp.json())
        assert validated.total == 1

    async def test_stats_group_by_dict_mixed_bucket_types(self) -> None:
        # Cover branch where buckets contains non-dict entries (284 else)
        svc = AsyncMock()
        svc.get_stats = AsyncMock(
            return_value={
                "total": 1,
                "buckets": ["not-a-dict", {"bucket": "2026-01-01", "count": 1}, 123],
            }
        )
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/stats?group_by=day")
        assert resp.status_code == 200
        # only dict bucket should be counted
        assert resp.json()["succeeded"] == 1
        assert resp.json()["results"][0]["bucket"] == "2026-01-01"


# ---------------------------------------------------------------------------
# Single GET /{id} -> 404 and success
# ---------------------------------------------------------------------------


class TestGetAuditLog:
    async def test_get_single_success_dto(self) -> None:
        dto = _make_audit_dto()
        svc = AsyncMock()
        svc.get_log = AsyncMock(return_value=dto)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{dto.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(dto.id)
        assert data["action"] == dto.action
        svc.get_log.assert_awaited_once_with(dto.id)

    async def test_get_single_not_found_none(self) -> None:
        svc = AsyncMock()
        svc.get_log = AsyncMock(return_value=None)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_get_single_not_found_attribute_error(self) -> None:
        svc = MagicMock()
        # No get_log attribute -> AttributeError
        del svc.get_log  # ensure attribute missing
        svc.get_log = MagicMock(side_effect=AttributeError("no method"))  # type: ignore[method-assign]
        # Actually need AsyncMock side_effect
        svc.get_log = AsyncMock(side_effect=AttributeError("missing"))  # type: ignore[method-assign]
        app = _create_audit_app(service_mock=svc)  # type: ignore[arg-type]
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_get_single_not_found_via_exception_message(self) -> None:
        svc = AsyncMock()
        svc.get_log = AsyncMock(side_effect=Exception("Audit log not found"))
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_get_single_generic_exception_500(self) -> None:
        svc = AsyncMock()
        svc.get_log = AsyncMock(side_effect=RuntimeError("db down"))
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 500
        assert "db down" in resp.json()["detail"]

    async def test_get_single_success_via_model_validate(self) -> None:
        svc = AsyncMock()
        # return object that is not AuditLogDTO but has attributes
        now = datetime.now(UTC)
        lid = uuid.uuid4()
        nid = uuid.uuid4()
        raw = MagicMock()
        raw.id = lid
        raw.node_id = nid
        raw.action = "update"
        raw.user = "bob"
        raw.details = "info"
        raw.created_at = now
        svc.get_log = AsyncMock(return_value=raw)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{lid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(lid)

    async def test_get_single_mapping_failure_500(self) -> None:
        svc = AsyncMock()
        # return object that will fail model_validate (missing fields)
        svc.get_log = AsyncMock(return_value=MagicMock(spec=[]))
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(f"/api/v2/audit/{uuid.uuid4()}")
        assert resp.status_code == 500
        assert "Failed to map" in resp.json()["detail"]

    async def test_get_single_invalid_uuid_422(self) -> None:
        svc = AsyncMock()
        svc.get_log = AsyncMock(return_value=None)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get("/api/v2/audit/not-a-uuid")
        assert resp.status_code == 422

    async def test_get_single_uses_audit_info(self) -> None:
        dto = _make_audit_dto()
        svc = AsyncMock()
        svc.get_log = AsyncMock(return_value=dto)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            with patch.object(audit_module.audit, "info") as mock_info:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-master"},
                ) as client:
                    resp = await client.get(f"/api/v2/audit/{dto.id}")
                assert resp.status_code == 200
                mock_info.assert_called()


# ---------------------------------------------------------------------------
# Direct module coverage: ensure all lines executed via import and calls
# ---------------------------------------------------------------------------


class TestDirectCoverage:
    async def test_list_calls_audit_info(self) -> None:
        svc = AsyncMock()
        svc.get_logs.return_value = AuditLogPageDTO(items=(), total=0)
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            with patch.object(audit_module.audit, "info") as mi:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-master"},
                ) as client:
                    await client.get("/api/v2/audit/?action=create")
                mi.assert_called()

    async def test_export_calls_audit_info(self) -> None:
        exp = AsyncMock()
        exp.export_audit.return_value = []
        app = _create_audit_app(exporter_mock=exp)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            with patch.object(audit_module.audit, "info") as mi:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-master"},
                ) as client:
                    await client.get("/api/v2/audit/exports?fmt=csv")
                mi.assert_called()

    async def test_stats_calls_audit_info(self) -> None:
        svc = AsyncMock()
        svc.get_stats = AsyncMock(return_value={"total": 0, "buckets": []})
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            with patch.object(audit_module.audit, "info") as mi:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-master"},
                ) as client:
                    await client.get("/api/v2/audit/stats?group_by=day")
                mi.assert_called()

    async def test_delete_calls_audit_info(self) -> None:
        svc = AsyncMock()
        svc.delete_all_logs.return_value = 0
        app = _create_audit_app(service_mock=svc)
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            with patch.object(audit_module.audit, "info") as mi:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={"X-API-Key": "test-master"},
                ) as client:
                    await client.delete("/api/v2/audit/?confirm=yes")
                mi.assert_called()

    async def test_list_with_user_filter_and_date(self) -> None:
        svc = AsyncMock()
        svc.get_logs.return_value = AuditLogPageDTO(items=(), total=1)
        app = _create_audit_app(service_mock=svc)
        dt = datetime(2026, 2, 1, tzinfo=UTC).isoformat()
        with patch(
            "app.api.deps.get_settings",
            return_value=_mock_settings("test-master"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as client:
                resp = await client.get(
                    "/api/v2/audit/",
                    params={"user": "admin", "date_from": dt, "date_to": dt},
                )
        assert resp.status_code == 200
        assert svc.get_logs.call_args.kwargs["user"] == "admin"
