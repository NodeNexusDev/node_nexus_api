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


@router.get("/{node_id}", response_model=NodeResponse)
@inject
async def get_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeManagementService],
    _principal: Principal = Security(get_current_principal),
) -> NodeResponse:
    """Get a node by ID."""
    audit.info("api.v2.nodes.get", node_id=str(node_id))
    return _node_response(await service.get_node(node_id))


@router.patch("/{node_id}", response_model=NodeResponse)
@inject
async def update_node(
    node_id: uuid.UUID,
    data: NodeUpdate,
    service: FromDishka[NodeManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> NodeResponse:
    """Update an existing node."""
    audit.info("api.v2.nodes.update", node_id=str(node_id))
    changes = data.model_dump(exclude_unset=True)
    if isinstance(changes.get("tags"), list):
        changes["tags"] = tuple(changes["tags"])
    dto = NodeUpdateDTO(changes=tuple(changes.items()))
    return _node_response(await service.update_node(node_id, dto))


@router.delete("/{node_id}", status_code=204)
@inject
async def delete_node(
    node_id: uuid.UUID,
    service: FromDishka[NodeManagementService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> None:
    """Delete a node."""
    audit.info("api.v2.nodes.delete", node_id=str(node_id))
    await service.delete_node(node_id)
