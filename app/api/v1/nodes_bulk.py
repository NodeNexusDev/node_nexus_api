"""Bulk node API endpoints."""

import asyncio
import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.bulk_node_operation import (
    BulkNodeDeleteDTO,
)
from app.application.dto.node_management import NodeUpdateDTO
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.schemas.node import (
    BulkNodeCheckRequest,
    BulkNodeDeleteRequest,
    BulkNodeMetricsRequest,
    BulkNodeMetricsResponse,
    BulkNodeMetricsResult,
    BulkNodeOperationResult,
    BulkNodeUpdateRequest,
    BulkNodeUpdateResponse,
    BulkNodeUpdateResult,
    BulkValidateCredentialsRequest,
    BulkValidateCredentialsResponse,
    BulkValidateCredentialsResult,
    CpuMetrics,
    DiskMetrics,
    LoadAverage,
    MemoryMetrics,
    NodeMetrics,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/nodes", tags=["nodes", "bulk"], route_class=DishkaRoute)


@router.post("/bulk/metrics", response_model=BulkNodeMetricsResponse)
@inject
async def bulk_get_node_metrics(
    data: BulkNodeMetricsRequest,
    service: FromDishka[NodeMetricsService],
    _key: str = Security(get_current_api_key),
) -> BulkNodeMetricsResponse:
    """Collect system metrics from multiple nodes in parallel."""
    audit.info(
        "api.nodes.bulk.metrics",
        node_ids=[str(n) for n in data.node_ids],
    )

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
        except Exception as exc:
            return BulkNodeMetricsResult(
                node_id=node_id,
                node_name="unknown",
                status="error",
                error=str(exc),
            )

    results = await asyncio.gather(
        *(_collect_one(node_id) for node_id in data.node_ids),
    )
    succeeded = sum(1 for r in results if r.status == "success")
    return BulkNodeMetricsResponse(
        results=list(results),
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.patch("/bulk/update", response_model=BulkNodeUpdateResponse)
@inject
async def bulk_update_nodes(
    data: BulkNodeUpdateRequest,
    service: FromDishka[NodeManagementService],
    _key: str = Security(require_write_scope),
) -> BulkNodeUpdateResponse:
    """Update multiple nodes with the same changes."""
    audit.info(
        "api.nodes.bulk_update",
        node_ids=[str(n) for n in data.node_ids],
    )

    changes = data.changes.model_dump(exclude_unset=True)
    if isinstance(changes.get("tags"), list):
        changes["tags"] = tuple(changes["tags"])

    async def _update_one(node_id: uuid.UUID) -> BulkNodeUpdateResult:
        try:
            await service.update_node(
                node_id,
                NodeUpdateDTO(changes=tuple(changes.items())),
            )
            return BulkNodeUpdateResult(node_id=node_id, status="success")
        except Exception as exc:
            return BulkNodeUpdateResult(node_id=node_id, status="error", error=str(exc))

    results = await asyncio.gather(
        *(_update_one(node_id) for node_id in data.node_ids),
    )
    succeeded = sum(1 for r in results if r.status == "success")
    return BulkNodeUpdateResponse(
        results=list(results),
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.post("/bulk/delete", response_model=BulkNodeOperationResult)
@inject
async def bulk_delete_nodes(
    data: BulkNodeDeleteRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Delete multiple nodes by IDs."""
    audit.info(
        "api.nodes.bulk_delete",
        node_ids=[str(n) for n in data.node_ids],
    )
    result = await service.bulk_delete(BulkNodeDeleteDTO(node_ids=tuple(data.node_ids)))
    return BulkNodeOperationResult(
        affected=result.affected,
        node_ids=list(result.node_ids),
    )


@router.post("/bulk/check", response_model=BulkNodeOperationResult)
@inject
async def bulk_check_nodes(
    data: BulkNodeCheckRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Check SSH connectivity for multiple nodes."""
    audit.info(
        "api.nodes.bulk_check",
        node_ids=[str(n) for n in data.node_ids],
    )
    result = await service.bulk_check(
        node_ids=tuple(str(n) for n in data.node_ids),
    )
    return BulkNodeOperationResult(
        affected=result.succeeded,
        node_ids=data.node_ids,
    )


@router.post(
    "/bulk/validate-credentials",
    response_model=BulkValidateCredentialsResponse,
)
@inject
async def bulk_validate_credentials(
    data: BulkValidateCredentialsRequest,
    service: FromDishka[NodeBulkCommandService],
    _key: str = Security(require_write_scope),
) -> BulkValidateCredentialsResponse:
    """Validate SSH connectivity for multiple existing nodes."""
    audit.info(
        "api.nodes.bulk_validate_credentials",
        node_ids=[str(n) for n in data.node_ids],
        tags=data.tags,
    )
    results_dto = await service.validate_credentials_bulk(
        node_ids=data.node_ids,
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
    return BulkValidateCredentialsResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )
