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


@router.get("/", response_model=NodeCursorListResponse)
@inject
async def list_nodes(
    service: FromDishka[NodeManagementService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    tag: str | None = Query(None, description="Filter by single tag"),
    search: str | None = Query(None, description="Search by name or host"),
    _principal: Principal = Security(get_current_principal),
) -> NodeCursorListResponse:
    """List nodes with cursor pagination.

    Uses common encode_cursor/decode_cursor. The service still exposes
    page/size internally for offset fallback; cursor is translated to offset
    when the underlying reader is offset-based.
    """
    tag_list = [tag] if tag else None
    decoded: tuple[datetime, uuid.UUID] | None = None
    if cursor is not None and cursor != "":
        try:
            decoded = decode_cursor(cursor)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid cursor") from None
    audit.info("api.v2.nodes.list", cursor=cursor, limit=limit, tag=tag, search=search)
    # Prefer cursor-based service; fallback translation to offset is handled
    # inside the service layer if needed. For now delegate directly to the
    # cursor use case.
    items, next_cursor_key, has_more = await service.get_nodes_cursor(
        cursor=decoded, limit=limit, tags=tag_list, search=search
    )
    next_cursor: str | None = None
    if next_cursor_key is not None:
        next_cursor = encode_cursor(*next_cursor_key)
    return NodeCursorListResponse(
        items=[_node_response(node) for node in items],
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Bulk create — POST / with 207 multi-status
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=BulkResult[NodeBulkCreateResult],
    status_code=201,
)
@inject
async def bulk_create_nodes(
    data: NodeBulkCreateRequest,
    service: FromDishka[NodeManagementService],
    response: Response,
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[NodeBulkCreateResult]:
    """Bulk create nodes (1..20). Returns 207 when partially succeeded."""
    audit.info("api.v2.nodes.bulk_create", count=len(data.items))

    async def _create_one(item: NodeCreate) -> NodeBulkCreateResult:
        try:
            dto = NodeCreateDTO(
                name=item.name,
                endpoint=NodeEndpoint(
                    host=item.host,
                    port=item.port,
                    connection_type=item.connection_type,
                    docker_host=item.docker_host,
                    has_docker=item.has_docker,
                ),
                credentials=NodeCredentials(
                    username=item.username,
                    password=item.password,
                    ssh_key=item.ssh_key,
                    passphrase=item.passphrase,
                ),
                tags=tuple(item.tags),
            )
            node = await service.create_node(dto)
            return NodeBulkCreateResult(node_id=node.id, status="success")
        except Exception as exc:  # noqa: BLE001
            return NodeBulkCreateResult(node_id=None, status="error", error=str(exc))

    results = await asyncio.gather(*(_create_one(item) for item in data.items))
    succeeded = sum(1 for r in results if r.status == "success")
    failed = len(results) - succeeded
    if failed > 0 and succeeded > 0:
        response.status_code = 207
    elif failed > 0:
        # keep 201? For bulk envelope use 200 on partial failure mix is 207,
        # pure failure still 200 per spec (failed>0 and succeeded>0 else 200).
        # But creation semantics prefer 200/207; override to 200 if spec says else 200.
        response.status_code = 200
    return BulkResult[NodeBulkCreateResult](
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=list(results),
    )


# ---------------------------------------------------------------------------
# Bulk update — PATCH / (collection) with 207
# ---------------------------------------------------------------------------


