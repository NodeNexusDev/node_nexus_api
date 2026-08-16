"""Execution lifecycle port."""

from __future__ import annotations

from typing import Protocol

from app.application.dto.execution_lifecycle import (
    CancelExecutionDTO,
)


class ExecutionLifecycleManager(Protocol):
    async def cancel_execution(self, data: CancelExecutionDTO) -> bool: ...
