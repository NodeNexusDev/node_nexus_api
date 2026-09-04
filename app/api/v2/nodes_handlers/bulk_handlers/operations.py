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


@router.patch("/", response_model=BulkResult[BulkNodeUpdateResult])
@inject
async def bulk_update_nodes(
    data: NodeBulkUpdatesRequest,
    service: FromDishka[NodeManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkNodeUpdateResult]:
    """Bulk update via PATCH /nodes (updates: [{id, changes}])."""
    audit.info("api.v2.nodes.bulk_update", count=len(data.updates))

    async def _update_one(
        node_id: uuid.UUID, changes_model: NodeUpdate
    ) -> BulkNodeUpdateResult:
        try:
            changes = changes_model.model_dump(exclude_unset=True)
            if isinstance(changes.get("tags"), list):
                changes["tags"] = tuple(changes["tags"])
            await service.update_node(
                node_id, NodeUpdateDTO(changes=tuple(changes.items()))
            )
            return BulkNodeUpdateResult(node_id=node_id, status="success")
        except Exception as exc:  # noqa: BLE001
            return BulkNodeUpdateResult(node_id=node_id, status="error", error=str(exc))

    results = await asyncio.gather(
        *(_update_one(item.id, item.changes) for item in data.updates)
    )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkNodeUpdateResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# Bulk delete — POST /deletions without bulk keyword
# ---------------------------------------------------------------------------


@router.post("/deletions", response_model=BulkResult[BulkNodeUpdateResult])
@inject
async def bulk_delete_nodes(
    data: NodeDeletionsRequest,
    service: FromDishka[NodeBulkOperationService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkNodeUpdateResult]:
    """Delete multiple nodes by IDs (no bulk keyword)."""
    audit.info("api.v2.nodes.deletions", ids=[str(i) for i in data.ids])
    result = await service.bulk_delete(BulkNodeDeleteDTO(node_ids=tuple(data.ids)))
    succeeded_ids = set(result.node_ids)
    results: list[BulkNodeUpdateResult] = []
    for nid in data.ids:
        if nid in succeeded_ids:
            results.append(BulkNodeUpdateResult(node_id=nid, status="success"))
        else:
            results.append(
                BulkNodeUpdateResult(
                    node_id=nid, status="error", error="Node not found"
                )
            )
    succeeded = len(succeeded_ids)
    failed = len(data.ids) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkNodeUpdateResult](
        total=len(data.ids),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Bulk checks — POST /checks
# ---------------------------------------------------------------------------


@router.post("/checks", response_model=BulkResult[BulkNodeUpdateResult])
@inject
async def bulk_check_nodes(
    data: NodeChecksRequest,
    service: FromDishka[NodeBulkOperationService],
    response: Response,
    mode: str = Query("ssh", description="Check mode: db or ssh"),
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkNodeUpdateResult]:
    """Check existence/connectivity for multiple nodes (no bulk keyword).

    Modes:
    - db: check existence in DB (legacy)
    - ssh: SSH connectivity check with status update (echo ok)
    """
    if mode not in ("db", "ssh"):
        raise HTTPException(status_code=422, detail="Invalid mode, use db or ssh")
    audit.info("api.v2.nodes.checks", ids=[str(i) for i in data.ids], mode=mode)
    result = await service.bulk_check(
        node_ids=tuple(str(n) for n in data.ids),
        mode=mode,  # type: ignore[arg-type]
    )
    succeeded_ids = (
        {uuid.UUID(str(x)) for x in result.node_ids} if result.node_ids else set()
    )
    # Service counts succeeded as existing nodes
    results: list[BulkNodeUpdateResult] = []
    for nid in data.ids:
        if nid in succeeded_ids:
            results.append(BulkNodeUpdateResult(node_id=nid, status="success"))
        else:
            results.append(
                BulkNodeUpdateResult(
                    node_id=nid, status="error", error="Node not found"
                )
            )
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    return BulkResult[BulkNodeUpdateResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# Bulk metrics — POST /metrics (asyncio.gather)
# ---------------------------------------------------------------------------
