"""Node API v2 — bulk-first without bulk keyword."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, HTTPException, Query, Response, Security

from app.api.deps import Principal, get_current_principal, require_write_or_jwt_scope
from app.application.dto.bulk_node_operation import BulkNodeDeleteDTO
from app.application.dto.node_management import NodeCreateDTO, NodeUpdateDTO
from app.application.dto.node_status_history import NodeStatusHistoryQueryDTO
from app.application.dto.node_validation import NodeValidationRequestDTO
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
from app.application.services.node_validation_service import NodeValidationService
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
    NodeValidateRequest,
    NodeValidateResponse,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/nodes", tags=["nodes"], route_class=DishkaRoute)


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


def _encode_offset(offset: int) -> str:
    """Encode an offset cursor for status-history pagination."""
    payload = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_offset(cursor: str) -> int:
    """Decode an offset cursor, raising ValueError on invalid input."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        data = json.loads(raw)
        return int(data["offset"])
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor}") from exc


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
    if cursor is not None:
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
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> BulkResult[BulkNodeUpdateResult]:
    """Check existence/connectivity for multiple nodes (no bulk keyword)."""
    audit.info("api.v2.nodes.checks", ids=[str(i) for i in data.ids])
    result = await service.bulk_check(node_ids=tuple(str(n) for n in data.ids))
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
# Validate single — POST /validate
# ---------------------------------------------------------------------------


@router.post("/validate", response_model=NodeValidateResponse)
@inject
async def validate_single(
    data: NodeValidateRequest,
    service: FromDishka[NodeValidationService],
    _principal: Principal = Security(require_write_or_jwt_scope),
) -> NodeValidateResponse:
    """Validate SSH credentials without saving a node."""
    audit.info("api.v2.nodes.validate", host=data.host, port=data.port)
    result = await service.validate_credentials(
        NodeValidationRequestDTO(
            endpoint=NodeEndpoint(
                host=data.host,
                port=data.port,
                connection_type=data.connection_type,
            ),
            credentials=NodeCredentials(
                username=data.username,
                password=data.password,
                ssh_key=data.ssh_key,
                passphrase=data.passphrase,
            ),
        )
    )
    return NodeValidateResponse(status=result.status, message=result.message)


# ---------------------------------------------------------------------------
# Status history — GET /{id}/status-history ?cursor&limit
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
    if cursor is not None:
        try:
            offset = _decode_offset(cursor)
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
    next_cursor = _encode_offset(offset + limit) if has_more else None
    return CursorPage[NodeStatusHistoryItem](
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Single node — GET /{node_id}, PATCH /{node_id}, DELETE /{node_id}
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
