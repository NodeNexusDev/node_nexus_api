"""Durable, idempotent delivery of transactional audit events."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.metrics import (
    AUDIT_DELIVERIES,
    AUDIT_FAILURES,
    AUDIT_OLDEST_PENDING,
    AUDIT_PENDING,
    AUDIT_RETRIES,
)
from app.models.audit_log import AuditLogModel
from app.models.audit_outbox import AuditOutboxModel
from app.models.node import NodeModel

logger = structlog.get_logger()


class AuditOutboxWorker:
    """Deliver pending outbox records to the immutable audit log."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        poll_seconds: float = 1.0,
        max_attempts: int = 5,
        batch_size: int = 100,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._poll_seconds = poll_seconds
        self._max_attempts = max_attempts
        self._batch_size = batch_size
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start one application-scoped delivery loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop delivery without abandoning an active transaction."""
        if self._task is None:
            return
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "audit.outbox.worker.failed",
                    error_type=type(exc).__name__,
                )
            await asyncio.sleep(self._poll_seconds)

    async def run_once(self) -> int:
        """Claim and deliver one due batch, returning successful deliveries."""
        now = datetime.now(UTC)
        delivered = 0
        async with self._sessionmaker() as session, session.begin():
            result = await session.execute(
                select(AuditOutboxModel)
                .where(
                    AuditOutboxModel.status == "pending",
                    AuditOutboxModel.next_attempt_at <= now,
                )
                .order_by(AuditOutboxModel.created_at)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            for event in result.scalars():
                if await self._deliver(session, event, now):
                    delivered += 1
            await self._update_metrics(session, now)
        return delivered

    async def _deliver(
        self, session: AsyncSession, event: AuditOutboxModel, now: datetime
    ) -> bool:
        event.attempts += 1
        if event.attempts > 1:
            AUDIT_RETRIES.inc()
        try:
            async with session.begin_nested():
                existing = await session.get(AuditLogModel, event.id)
                if existing is None:
                    session.add(
                        await self._to_audit_log(session, event.id, event.payload)
                    )
                    await session.flush()
        except Exception as exc:
            AUDIT_FAILURES.inc()
            event.last_error_type = type(exc).__name__
            if event.attempts >= self._max_attempts:
                event.status = "failed"
            else:
                delay = min(300, 2 ** (event.attempts - 1))
                event.next_attempt_at = now + timedelta(seconds=delay)
            logger.warning(
                "audit.outbox.delivery.failed",
                event_id=str(event.id),
                attempts=event.attempts,
                error_type=type(exc).__name__,
            )
            return False
        event.status = "completed"
        event.last_error_type = None
        event.delivered_at = now
        AUDIT_DELIVERIES.inc()
        return True

    @staticmethod
    async def _to_audit_log(
        session: AsyncSession, event_id: UUID, payload: dict[str, Any]
    ) -> AuditLogModel:
        node_id = payload.get("node_id")
        parsed_node_id = UUID(node_id) if node_id else None
        if parsed_node_id is not None:
            node_exists = await session.get(NodeModel, parsed_node_id)
            if node_exists is None:
                parsed_node_id = None
        return AuditLogModel(
            id=event_id,
            node_id=parsed_node_id,
            action=payload["action"],
            user=payload.get("user"),
            details=payload.get("details"),
        )

    @staticmethod
    async def _update_metrics(session: AsyncSession, now: datetime) -> None:
        pending, oldest = (
            await session.execute(
                select(
                    func.count(AuditOutboxModel.id),
                    func.min(AuditOutboxModel.created_at),
                ).where(AuditOutboxModel.status == "pending")
            )
        ).one()
        AUDIT_PENDING.set(pending)
        age = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
        AUDIT_OLDEST_PENDING.set(age)
