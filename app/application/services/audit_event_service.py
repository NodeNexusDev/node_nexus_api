"""Application service for optional and required audit events."""

from typing import Any
from uuid import UUID

from app.application.dto.audit import AuditEventDTO
from app.application.policies.audit import sanitize_audit_details
from app.application.ports.audit_log import AuditOutboxPort
from app.core.exceptions import AuditWriteError


class AuditEventService:
    """Sanitize and append audit events through explicit outbox boundaries."""

    def __init__(
        self,
        optional_outbox: AuditOutboxPort,
        required_outbox: AuditOutboxPort,
    ) -> None:
        self._optional_outbox = optional_outbox
        self._required_outbox = required_outbox

    async def log(
        self,
        action: str,
        node_id: UUID | None = None,
        user: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            await self._optional_outbox.enqueue(
                self._event(action, node_id, user, details)
            )
        except Exception as exc:
            raise AuditWriteError("Audit event could not be persisted") from exc

    async def log_required(
        self,
        action: str,
        node_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        try:
            await self._required_outbox.enqueue(
                self._event(action, node_id, None, details)
            )
        except Exception as exc:
            raise AuditWriteError(
                "Required audit event could not be committed"
            ) from exc

    @staticmethod
    def _event(
        action: str,
        node_id: UUID | None,
        user: str | None,
        details: dict[str, Any] | None,
    ) -> AuditEventDTO:
        return AuditEventDTO(
            action=action,
            node_id=node_id,
            user=user,
            details=sanitize_audit_details(details) if details else None,
        )
