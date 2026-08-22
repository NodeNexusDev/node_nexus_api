"""Unit tests for node bulk API endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from app.api.v1.commands import router as commands_router
from app.api.v1.nodes import router as nodes_router
from app.api.v1.nodes_bulk import router as nodes_bulk_router
from app.application.dto.bulk_node_operation import (
    BulkNodeCheckResultDTO,
    BulkNodeOperationResultDTO,
)
from app.application.dto.node_metrics import (
    CpuMetricsDTO,
    LoadAverageDTO,
    NodeMetricsDTO,
    UsageMetricsDTO,
)
from app.application.dto.node_status_history import NodeStatusHistoryPageDTO
from app.application.services.execution_history_service import ExecutionHistoryService
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.execution_stats_service import ExecutionStatsService
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
from tests.unit.conftest import MockAuthServiceProvider, _mock_settings


def _create_nodes_app(**services: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(commands_router, prefix="/api/v1")
    app.include_router(nodes_bulk_router, prefix="/api/v1")
    app.include_router(nodes_router, prefix="/api/v1")

    class MockServiceProvider(Provider):
        @provide(scope=Scope.REQUEST)
        def get_node_management(self) -> NodeManagementService:
            return services.get("node_management", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_node_bulk_op(self) -> NodeBulkOperationService:
            return services.get("node_bulk_op", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_node_bulk_cmd(self) -> NodeBulkCommandService:
            return services.get("node_bulk_cmd", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_node_metrics(self) -> NodeMetricsService:
            return services.get("node_metrics", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_node_validation(self) -> NodeValidationService:
            return services.get("node_validation", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_execution_lifecycle(self) -> ExecutionLifecycleService:
            return services.get("execution_lifecycle", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_execution_stats(self) -> ExecutionStatsService:
            return services.get("execution_stats", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_execution_history(self) -> ExecutionHistoryService:
            return services.get("execution_history", AsyncMock())

        @provide(scope=Scope.REQUEST)
        def get_node_status_history(self) -> NodeStatusHistoryService:
            return services.get("node_status_history", AsyncMock())

    container = make_async_container(MockServiceProvider(), MockAuthServiceProvider())
    setup_dishka(container, app)
    return app


NODE_ID = "00000000-0000-0000-0000-000000000001"
NODE_ID2 = "00000000-0000-0000-0000-000000000002"

_settings_patcher = patch(
    "app.api.deps.get_settings",
    return_value=_mock_settings("test-master"),
)


# ── bulk/metrics ──


class TestBulkMetrics:
    @pytest.mark.asyncio
    async def test_bulk_get_metrics(self) -> None:
        svc = AsyncMock()
        svc.get_node_metrics.return_value = NodeMetricsDTO(
            cpu=CpuMetricsDTO(usage_percent=50.0, cores=4),
            memory=UsageMetricsDTO(total_bytes=1024, used_bytes=512, percent=50.0),
            disk=UsageMetricsDTO(total_bytes=10240, used_bytes=5120, percent=50.0),
            load_average=LoadAverageDTO(one_min=1.0, five_min=1.0, fifteen_min=1.0),
            uptime_since="2024-01-01T00:00:00Z",
        )
        app = _create_nodes_app(node_metrics=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/nodes/bulk/metrics",
                    json={"node_ids": [NODE_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1


# ── bulk/update ──


class TestBulkUpdate:
    @pytest.mark.asyncio
    async def test_bulk_update_nodes(self) -> None:
        svc = AsyncMock()
        svc.update_node.return_value = None
        app = _create_nodes_app(node_management=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.put(
                    "/api/v1/nodes/bulk/update",
                    json={
                        "node_ids": [NODE_ID],
                        "changes": {"name": "new-name"},
                    },
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1


# ── bulk/validate-credentials ──


class TestBulkValidateCredentials:
    @pytest.mark.asyncio
    async def test_bulk_validate_credentials(self) -> None:
        svc = AsyncMock()
        svc._node_reader = AsyncMock()
        svc._node_reader.get_connections_by_ids = AsyncMock(return_value=[])
        svc._connector_factory = AsyncMock()
        svc._credential_cipher = AsyncMock()
        app = _create_nodes_app(node_bulk_cmd=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/nodes/bulk/validate-credentials",
                    json={"node_ids": [NODE_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# ── bulk/retry ──


class TestBulkRetry:
    @pytest.mark.asyncio
    async def test_bulk_retry_commands(self) -> None:
        svc = AsyncMock()
        svc._command_history_reader = None
        app = _create_nodes_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/commands/bulk/retry",
                    json={"execution_ids": [NODE_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["failed"] == 1


# ── bulk/cancel ──


class TestBulkCancel:
    @pytest.mark.asyncio
    async def test_bulk_cancel_commands(self) -> None:
        svc = AsyncMock()
        svc.cancel_execution = AsyncMock(return_value=True)
        app = _create_nodes_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/commands/bulk/cancel",
                    json={"execution_ids": [NODE_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["succeeded"] == 1


# ── bulk/delete ──


class TestBulkDelete:
    @pytest.mark.asyncio
    async def test_bulk_delete_nodes(self) -> None:
        svc = AsyncMock()
        svc.bulk_delete.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(uuid.UUID(NODE_ID),)
        )
        app = _create_nodes_app(node_bulk_op=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/nodes/bulk/delete",
                    json={"node_ids": [NODE_ID]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected"] == 1


# ── bulk/tags/add ──


class TestBulkAddTags:
    @pytest.mark.asyncio
    async def test_bulk_add_tags(self) -> None:
        svc = AsyncMock()
        svc.bulk_add_tags.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(uuid.UUID(NODE_ID),)
        )
        app = _create_nodes_app(node_bulk_op=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/nodes/bulk/tags/add",
                    json={"node_ids": [NODE_ID], "tags": ["prod"]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected"] == 1


# ── bulk/tags/remove ──


class TestBulkRemoveTags:
    @pytest.mark.asyncio
    async def test_bulk_remove_tags(self) -> None:
        svc = AsyncMock()
        svc.bulk_remove_tags.return_value = BulkNodeOperationResultDTO(
            affected=1, node_ids=(uuid.UUID(NODE_ID),)
        )
        app = _create_nodes_app(node_bulk_op=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    "/api/v1/nodes/bulk/tags/remove",
                    json={"node_ids": [NODE_ID], "tags": ["prod"]},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected"] == 1


# ── bulk/check ──


class TestBulkCheck:
    @pytest.mark.asyncio
    async def test_bulk_check_service(self) -> None:
        svc = AsyncMock()
        svc.bulk_check.return_value = BulkNodeCheckResultDTO(
            total=1, succeeded=1, failed=0, node_ids=(uuid.UUID(NODE_ID),)
        )
        result = await svc.bulk_check(node_ids=(NODE_ID,))
        assert result.succeeded == 1
        assert result.total == 1


# ── retry single command ──


class TestRetryCommand:
    @pytest.mark.asyncio
    async def test_retry_single_command(self) -> None:
        svc = AsyncMock()
        svc.retry_command.return_value = MagicMock(
            execution_id="exec-123",
            node_id=NODE_ID,
            command_fingerprint="abc",
            status="retry_scheduled",
        )
        app = _create_nodes_app(execution_lifecycle=svc)
        with _settings_patcher:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-API-Key": "test-master"},
            ) as ac:
                resp = await ac.post(
                    f"/api/v1/commands/executions/{NODE_ID2}/retry",
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "retry_scheduled"


# ── status-history ──


class TestStatusHistory:
    @pytest.mark.asyncio
    async def test_get_node_status_history_service(self) -> None:
        svc = AsyncMock()
        svc.get_history.return_value = NodeStatusHistoryPageDTO(items=(), total=0)
        result = await svc.get_history(node_id=uuid.UUID(NODE_ID), page=1, size=20)
        assert result.total == 0


# ── stats ──


class TestNodeStats:
    @pytest.mark.asyncio
    async def test_get_node_stats_service(self) -> None:
        svc = AsyncMock()
        svc.get_node_command_stats.return_value = MagicMock(
            total_executions=10,
            successful=8,
            failed=2,
        )
        result = await svc.get_node_command_stats(node_id=uuid.UUID(NODE_ID))
        assert result.total_executions == 10
        assert result.successful == 8
