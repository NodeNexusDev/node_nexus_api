"""Audit log service for tracking operations."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AuditWriteError
from app.repositories.audit_repo import AuditLogRepository
from app.schemas.audit_log import AuditLogResponse

audit = structlog.get_logger("audit")
_SENSITIVE_DETAIL_KEYS = {
    "password",
    "ssh_key",
    "token",
    "api_key",
    "authorization",
    "command",
    "params",
    "stdout",
    "stderr",
}


def sanitize_audit_details(details: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive runtime payloads from durable audit details."""
    return {
        key: value
        for key, value in details.items()
        if key.lower() not in _SENSITIVE_DETAIL_KEYS
    }


class RequiredAuditWriter:
    """Persist obligatory intents in an independent short transaction."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def write(self, data: dict[str, Any]) -> None:
        """Commit one outbox event without affecting the request transaction."""
        async with self._sessionmaker() as session, session.begin():
            await AuditLogRepository(session).create(data)


class AuditService:
    """Service for audit log operations."""

    def __init__(
        self,
        repository: AuditLogRepository,
        required_writer: RequiredAuditWriter | None = None,
    ):
        self._repository = repository
        self._required_writer = required_writer

    async def log(
        self,
        action: str,
        node_id: UUID | None = None,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Persist an obligatory audit event in the request transaction."""
        try:
            safe_details = sanitize_audit_details(details) if details else None
            await self._repository.create(
                {
                    "node_id": node_id,
                    "action": action,
                    "user": user,
                    "details": json.dumps(safe_details) if safe_details else None,
                }
            )
            audit.debug(
                "audit.log.ok",
                action=action,
                node_id=str(node_id) if node_id else None,
            )
        except Exception as exc:
            audit.error(
                "audit.log.failed",
                action=action,
                node_id=str(node_id) if node_id else None,
                error_type=type(exc).__name__,
            )
            raise AuditWriteError("Audit event could not be persisted") from exc

    async def log_required(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Durably commit an audit intent before an external side effect."""
        try:
            safe_details = sanitize_audit_details(details) if details else None
            data = {
                "node_id": node_id,
                "action": action,
                "user": None,
                "details": json.dumps(safe_details) if safe_details else None,
            }
            if self._required_writer is not None:
                await self._required_writer.write(data)
            else:
                await self._repository.create(data)
                await self._repository.commit()
        except Exception as exc:
            audit.error(
                "audit.required.commit_failed",
                action=action,
                node_id=str(node_id) if node_id else None,
                error_type=type(exc).__name__,
            )
            raise AuditWriteError(
                "Required audit event could not be committed"
            ) from exc

    async def get_logs(
        self,
        node_id: UUID | None = None,
        action: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[AuditLogResponse], int]:
        """Get audit logs with pagination."""
        skip = (page - 1) * size
        logs = await self._repository.get_all(
            node_id=node_id, action=action, skip=skip, limit=size
        )
        total = await self._repository.count(node_id=node_id, action=action)
        return [AuditLogResponse.model_validate(log) for log in logs], total

    async def cleanup_old_logs(self, retention_days: int) -> int:
        """Delete audit logs older than retention_days.

        Returns:
            Number of deleted rows.
        """
        if retention_days <= 0:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted = await self._repository.delete_before(cutoff)
        if deleted > 0:
            audit.info(
                "audit.cleanup.ok",
                deleted=deleted,
                retention_days=retention_days,
            )
        return deleted

    async def delete_all_logs(self) -> int:
        """Delete all audit log entries.

        Returns:
            Number of deleted rows.
        """
        from datetime import datetime as dt

        deleted = await self._repository.delete_before(dt.max.replace(tzinfo=UTC))
        audit.info("audit.delete_all.ok", deleted=deleted)
        return deleted
