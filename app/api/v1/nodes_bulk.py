"""Bulk node API endpoints."""

import asyncio
import uuid
from typing import Annotated

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Query, Security

from app.api.deps import get_current_api_key, require_write_scope
from app.application.dto.bulk_node_operation import (
    BulkNodeDeleteDTO,
    BulkNodeTagOperationDTO,
)
from app.application.dto.command_execution import BulkCommandRequestDTO
from app.application.dto.execution_lifecycle import CancelExecutionDTO, RetryCommandDTO
from app.application.dto.node_management import NodeUpdateDTO
from app.application.services.bulk_command_history_service import (
    BulkCommandHistoryService,
)
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.application.services.node_bulk_command_service import NodeBulkCommandService
from app.application.services.node_bulk_operation_service import (
    NodeBulkOperationService,
)
from app.application.services.node_management_service import NodeManagementService
from app.application.services.node_metrics_service import NodeMetricsService
from app.schemas.node import (
    BulkCancelCommandRequest,
    BulkCancelCommandResponse,
    BulkCancelCommandResult,
    BulkCommandHistoryItem,
    BulkCommandHistoryResponse,
    BulkCommandRequest,
    BulkCommandResult,
    BulkNodeCheckRequest,
    BulkNodeDeleteRequest,
    BulkNodeMetricsRequest,
    BulkNodeMetricsResponse,
    BulkNodeMetricsResult,
    BulkNodeOperationResult,
    BulkNodeResult,
    BulkNodeTagRequest,
    BulkNodeUpdateRequest,
    BulkNodeUpdateResponse,
    BulkNodeUpdateResult,
    BulkRetryCommandRequest,
    BulkRetryCommandResponse,
    BulkRetryCommandResult,
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


@router.post("/bulk/execute", response_model=BulkCommandResult)
@inject
async def bulk_execute_command(
    data: BulkCommandRequest,
    service: FromDishka[NodeBulkCommandService],
    _key: str = Security(require_write_scope),
) -> BulkCommandResult:
    """Execute a command on multiple nodes by IDs and/or tags."""
    audit.info(
        "api.nodes.bulk_execute",
        command=data.command,
        node_ids=[str(n) for n in (data.node_ids or [])],
        tags=data.tags,
    )
    result = await service.bulk_execute_command(
        BulkCommandRequestDTO(
            command=data.command,
            node_ids=tuple(data.node_ids or ()),
            tags=tuple(data.tags or ()),
        )
    )
    return BulkCommandResult(
        command=result.command,
        results=[
            BulkNodeResult(
                node_id=item.node_id,
                node_name=item.node_name,
                stdout=item.stdout,
                stderr=item.stderr,
                exit_code=item.exit_code,
            )
            for item in result.results
        ],
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
    )


@router.get("/bulk/history", response_model=BulkCommandHistoryResponse)
@inject
async def get_bulk_command_history(
    batch_id: Annotated[uuid.UUID, Query(description="Batch ID to retrieve")],
    service: FromDishka[BulkCommandHistoryService],
    _key: str = Security(get_current_api_key),
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> BulkCommandHistoryResponse:
    """Return paginated command execution history for one bulk batch."""
    audit.info(
        "api.nodes.bulk.history",
        batch_id=str(batch_id),
        page=page,
        size=size,
    )
    result = await service.get_batch_history(batch_id, page=page, size=size)
    return BulkCommandHistoryResponse(
        items=[BulkCommandHistoryItem.model_validate(item) for item in result.items],
        total=result.total,
        page=page,
        size=size,
    )


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


@router.put("/bulk/update", response_model=BulkNodeUpdateResponse)
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


@router.post("/bulk/tags/add", response_model=BulkNodeOperationResult)
@inject
async def bulk_add_tags(
    data: BulkNodeTagRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Add tags to multiple nodes."""
    audit.info(
        "api.nodes.bulk_tags_add",
        node_ids=[str(n) for n in data.node_ids],
        tags=data.tags,
    )
    result = await service.bulk_add_tags(
        BulkNodeTagOperationDTO(
            node_ids=tuple(data.node_ids),
            tags=tuple(data.tags),
        )
    )
    return BulkNodeOperationResult(
        affected=result.affected,
        node_ids=list(result.node_ids),
    )


@router.post("/bulk/tags/remove", response_model=BulkNodeOperationResult)
@inject
async def bulk_remove_tags(
    data: BulkNodeTagRequest,
    service: FromDishka[NodeBulkOperationService],
    _key: str = Security(require_write_scope),
) -> BulkNodeOperationResult:
    """Remove tags from multiple nodes."""
    audit.info(
        "api.nodes.bulk_tags_remove",
        node_ids=[str(n) for n in data.node_ids],
        tags=data.tags,
    )
    result = await service.bulk_remove_tags(
        BulkNodeTagOperationDTO(
            node_ids=tuple(data.node_ids),
            tags=tuple(data.tags),
        )
    )
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
    from app.application.dto.node_connection import NodeConnectionDTO
    from app.application.services._target_resolver import resolve_targets

    audit.info(
        "api.nodes.bulk_validate_credentials",
        node_ids=[str(n) for n in data.node_ids],
        tags=data.tags,
    )
    nodes = await resolve_targets(
        service._node_reader,
        node_ids=data.node_ids,
        tags=data.tags,
    )

    async def _validate_one(node: NodeConnectionDTO) -> BulkValidateCredentialsResult:
        try:
            connector = service._connector_factory.create_ssh(
                host=node.host,
                port=node.port,
                username=node.username,
                password=service._credential_cipher.decrypt(node.password),
                ssh_key=service._credential_cipher.decrypt(node.ssh_key),
                passphrase=service._credential_cipher.decrypt(node.passphrase),
            )
            async with connector:
                await connector.execute_command("echo ok")
            return BulkValidateCredentialsResult(
                node_id=node.id,
                node_name=node.name,
                status="success",
                message="Credentials valid",
            )
        except Exception as exc:
            return BulkValidateCredentialsResult(
                node_id=node.id,
                node_name=node.name,
                status="error",
                message=str(exc),
            )

    results = list(await asyncio.gather(*(_validate_one(node) for node in nodes)))
    succeeded = sum(1 for r in results if r.status == "success")
    return BulkValidateCredentialsResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.post(
    "/bulk/retry",
    response_model=BulkRetryCommandResponse,
)
@inject
async def bulk_retry_commands(
    data: BulkRetryCommandRequest,
    service: FromDishka[ExecutionLifecycleService],
    _key: str = Security(require_write_scope),
) -> BulkRetryCommandResponse:
    """Retry multiple command executions."""
    audit.info(
        "api.nodes.bulk_retry_commands",
        execution_ids=[str(e) for e in data.execution_ids],
    )

    async def _retry_one(execution_id: uuid.UUID) -> BulkRetryCommandResult:
        try:
            reader = service._command_history_reader
            if reader is None:
                return BulkRetryCommandResult(
                    execution_id=str(execution_id),
                    status="error",
                    message="Command history reader not available",
                )
            execution = await reader.get_by_id(execution_id)
            if execution is None:
                return BulkRetryCommandResult(
                    execution_id=str(execution_id),
                    status="error",
                    message="Execution not found",
                )
            if execution.node_id is None:
                return BulkRetryCommandResult(
                    execution_id=str(execution_id),
                    status="error",
                    message="No node_id associated with execution",
                )
            await service.retry_command(
                RetryCommandDTO(
                    execution_id=execution_id,
                    node_id=execution.node_id,
                )
            )
            return BulkRetryCommandResult(
                execution_id=str(execution_id),
                status="retry_scheduled",
            )
        except Exception as exc:
            return BulkRetryCommandResult(
                execution_id=str(execution_id),
                status="error",
                message=str(exc),
            )

    results = list(
        await asyncio.gather(*(_retry_one(eid) for eid in data.execution_ids))
    )
    succeeded = sum(1 for r in results if r.status == "retry_scheduled")
    return BulkRetryCommandResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.post(
    "/bulk/cancel",
    response_model=BulkCancelCommandResponse,
)
@inject
async def bulk_cancel_commands(
    data: BulkCancelCommandRequest,
    service: FromDishka[ExecutionLifecycleService],
    _key: str = Security(require_write_scope),
) -> BulkCancelCommandResponse:
    """Cancel multiple running command executions."""
    audit.info(
        "api.nodes.bulk_cancel_commands",
        execution_ids=[str(e) for e in data.execution_ids],
    )

    async def _cancel_one(execution_id: uuid.UUID) -> BulkCancelCommandResult:
        try:
            await service.cancel_execution(
                CancelExecutionDTO(execution_id=execution_id)
            )
            return BulkCancelCommandResult(
                execution_id=str(execution_id),
                status="cancelled",
            )
        except Exception as exc:
            return BulkCancelCommandResult(
                execution_id=str(execution_id),
                status="error",
                message=str(exc),
            )

    results = list(
        await asyncio.gather(*(_cancel_one(eid) for eid in data.execution_ids))
    )
    succeeded = sum(1 for r in results if r.status == "cancelled")
    return BulkCancelCommandResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )
