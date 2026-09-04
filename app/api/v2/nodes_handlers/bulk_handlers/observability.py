# ruff: noqa: F401, I001
"""Node API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.api.pagination import decode_offset, encode_offset
from app.application.dto.bulk_node_operation import BulkNodeDeleteDTO
from app.application.dto.node_management import NodeCreateDTO, NodeUpdateDTO
from app.application.dto.node_status_history import NodeStatusHistoryQueryDTO
from app.application.dto.node_view import NodeViewDTO
from app.application.dto.value_objects import NodeCredentials, NodeEndpoint
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.application.services.node_status_history_service import (
    NodeStatusHistoryService,
)
from app.schemas.common import BulkResult, CursorPage, decode_cursor, encode_cursor
from app.schemas.node import (
    BulkNodeMetricsResult,
    BulkNodeUpdateResult,
    BulkValidateCredentialsResult,
    CpuMetrics,
    CredentialValidationsRequest,
    DiskMetrics,
    LoadAverage,
    MemoryMetrics,
    NodeBulkCreateRequest,
    NodeBulkCreateResult,
    NodeBulkUpdatesRequest,
    NodeChecksRequest,
    NodeCreate,
    NodeCursorListResponse,
    NodeDeletionsRequest,
    NodeMetrics,
    NodeMetricsRequest,
    NodeResponse,
    NodeStatusHistoryItem,
    NodeUpdate,
)

audit = structlog.get_logger("audit")

# Compatibility aliases for tests importing private helpers
_encode_offset = encode_offset  # noqa: N816
_decode_offset = decode_offset  # noqa: N816

router = APIRouter(route_class=DishkaRoute)


def _node_response(node: NodeViewDTO) -> NodeResponse:
    """Map an application node view to the HTTP response schema."""
    return NodeResponse(
        id=node.id,
        name=node.name,
        host=node.endpoint.host,
        port=node.endpoint.port,
        connection_type=node.endpoint.connection_type,
        status=node.status,
        username=node.username,
        docker_host=node.endpoint.docker_host,
        has_docker=node.endpoint.has_docker,
        tags=list(node.tags),
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


# ---------------------------------------------------------------------------
# List — cursor pagination (bulk-first, no bulk keyword)
# ---------------------------------------------------------------------------


@router.post("/metrics", response_model=BulkResult[BulkNodeMetricsResult])
@inject
async def bulk_get_node_metrics(
    data: NodeMetricsRequest,
    service: FromDishka[NodeMetricsService],
    response: Response,
    _principal: Principal = Security(get_current_principal),
) -> BulkResult[BulkNodeMetricsResult]:
    """Collect system metrics from multiple nodes in parallel (no bulk keyword)."""
    audit.info("api.v2.nodes.metrics", ids=[str(n) for n in data.ids])

    async def _collect_one(node_id: uuid.UUID) -> BulkNodeMetricsResult:
        try:
            result = await service.get_node_metrics(node_id)
            return BulkNodeMetricsResult(
                node_id=node_id,
                node_name="unknown",
                status="success",
                metrics=NodeMetrics(
                    cpu=CpuMetrics(
                        usage_percent=result.cpu.usage_percent,
                        cores=result.cpu.cores,
                    ),
                    memory=MemoryMetrics(
                        total_bytes=result.memory.total_bytes,
                        used_bytes=result.memory.used_bytes,
                        percent=result.memory.percent,
                    ),
                    disk=DiskMetrics(
                        total_bytes=result.disk.total_bytes,
                        used_bytes=result.disk.used_bytes,
                        percent=result.disk.percent,
                    ),
                    load_average=LoadAverage(
                        one_min=result.load_average.one_min,
                        five_min=result.load_average.five_min,
                        fifteen_min=result.load_average.fifteen_min,
                    ),
                    uptime_since=result.uptime_since,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return BulkNodeMetricsResult(
                node_id=node_id,
                node_name="unknown",
                status="error",
                error=str(exc),
            )

    results = await asyncio.gather(*(_collect_one(nid) for nid in data.ids))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkNodeMetricsResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# Credential validations — POST /credential-validations
# ---------------------------------------------------------------------------


@router.post(
    "/credential-validations",
    response_model=BulkResult[BulkValidateCredentialsResult],
)
@inject
async def credential_validations(
    data: CredentialValidationsRequest,
    service: FromDishka[NodeBulkCommandService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkValidateCredentialsResult]:
    """Validate credentials for multiple nodes (no bulk keyword)."""
    audit.info(
        "api.v2.nodes.credential_validations",
        ids=[str(n) for n in data.ids] if data.ids else None,
        tags=data.tags,
    )
    results_dto = await service.validate_credentials_bulk(
        node_ids=data.ids,
        tags=data.tags,
    )
    results = [
        BulkValidateCredentialsResult(
            node_id=r.node_id,
            node_name=r.node_name,
            status=r.status,
            message=r.message,
        )
        for r in results_dto
    ]
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkValidateCredentialsResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Status history — GET /{id}/status-history ?cursor&limit
# ---------------------------------------------------------------------------


