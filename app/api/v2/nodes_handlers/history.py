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


@router.get(
    "/{node_id}/status-history",
    response_model=CursorPage[NodeStatusHistoryItem],
)
@inject
async def get_node_status_history(
    node_id: uuid.UUID,
    service: FromDishka[NodeStatusHistoryService],
    cursor: str | None = Query(None, description="Opaque cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size for cursor pagination"),
    _principal: Principal = Security(get_current_principal),
) -> CursorPage[NodeStatusHistoryItem]:
    """Get status change history for a node with cursor pagination.

    Cursor encodes an offset. Delegates to the offset-based service by
    translating cursor -> offset internally.
    """
    audit.info(
        "api.v2.nodes.status_history",
        node_id=str(node_id),
        cursor=cursor,
        limit=limit,
    )
    offset = 0
    if cursor is not None and cursor != "":
        try:
            offset = decode_offset(cursor)
        except ValueError:
            try:
                _ = decode_cursor(cursor)
                offset = 0
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid cursor") from None
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(status_code=422, detail="Invalid cursor") from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=422, detail="Invalid cursor") from exc
    query = NodeStatusHistoryQueryDTO(node_id=node_id, offset=offset, limit=limit)
    result = await service.get_history(query)
    items = [
        NodeStatusHistoryItem(
            id=item.id,
            node_id=item.node_id,
            old_status=item.old_status,
            new_status=item.new_status,
            source=item.source,
            changed_at=item.changed_at,
        )
        for item in result.items
    ]
    has_more = (offset + len(items)) < result.total
    next_cursor = encode_offset(offset + limit) if has_more else None
    return CursorPage[NodeStatusHistoryItem](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Single node — GET /{node_id}, PATCH /{node_id}, DELETE /{node_id}
# ---------------------------------------------------------------------------


