"""Bulk script execution lifecycle endpoints."""

import asyncio
import uuid

import structlog
from dishka.integrations.fastapi import DishkaRoute, FromDishka, inject
from fastapi import APIRouter, Security

from app.api.deps import (
    Principal,
    require_write_or_jwt_scope,
)
from app.application.dto.execution_lifecycle import (
    CancelExecutionDTO,
    RetryScriptDTO,
)
from app.application.services.execution_lifecycle_service import (
    ExecutionLifecycleService,
)
from app.schemas.script import (
    ScriptBulkCancelRequest,
    ScriptBulkOperationResponse,
    ScriptBulkResult,
    ScriptBulkRetryRequest,
)

audit = structlog.get_logger("audit")

router = APIRouter(prefix="/scripts", tags=["scripts"], route_class=DishkaRoute)


@router.post("/bulk/retry", response_model=ScriptBulkOperationResponse)
@inject
async def bulk_retry_scripts(
    data: ScriptBulkRetryRequest,
    service: FromDishka[ExecutionLifecycleService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> ScriptBulkOperationResponse:
    """Retry multiple script executions."""
    execution_ids = [uuid.UUID(str(eid)) for eid in data.execution_ids]

    audit.info(
        "api.scripts.bulk_retry",
        execution_ids=[str(e) for e in execution_ids],
    )

    async def _retry_one(execution_id: uuid.UUID) -> ScriptBulkResult:
        try:
            result = await service.retry_script(
                RetryScriptDTO(execution_id=execution_id)
            )
            return ScriptBulkResult(
                execution_id=result.execution_id,
                status=result.status,
                message="Script retry scheduled",
            )
        except Exception as exc:
            return ScriptBulkResult(
                execution_id=str(execution_id),
                status="error",
                message=str(exc),
            )

    results = list(await asyncio.gather(*(_retry_one(eid) for eid in execution_ids)))
    succeeded = sum(1 for r in results if r.status == "retry_scheduled")
    return ScriptBulkOperationResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


@router.post("/bulk/cancel", response_model=ScriptBulkOperationResponse)
@inject
async def bulk_cancel_scripts(
    data: ScriptBulkCancelRequest,
    service: FromDishka[ExecutionLifecycleService],
    _key: Principal = Security(require_write_or_jwt_scope),
) -> ScriptBulkOperationResponse:
    """Cancel multiple running script executions."""
    execution_ids = [uuid.UUID(str(eid)) for eid in data.execution_ids]

    audit.info(
        "api.scripts.bulk_cancel",
        execution_ids=[str(e) for e in execution_ids],
    )

    async def _cancel_one(execution_id: uuid.UUID) -> ScriptBulkResult:
        try:
            await service.cancel_execution(
                CancelExecutionDTO(execution_id=execution_id)
            )
            return ScriptBulkResult(
                execution_id=str(execution_id),
                status="cancelled",
                message="Execution cancelled",
            )
        except Exception as exc:
            return ScriptBulkResult(
                execution_id=str(execution_id),
                status="error",
                message=str(exc),
            )

    results = list(await asyncio.gather(*(_cancel_one(eid) for eid in execution_ids)))
    succeeded = sum(1 for r in results if r.status == "cancelled")
    return ScriptBulkOperationResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )
