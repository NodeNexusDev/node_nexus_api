"""Application audit event port."""

from typing import Protocol
from uuid import UUID

from app.application.types import JsonObject


class AuditEventSink(Protocol):
    """Persist optional results and required pre-side-effect audit intents."""

    async def log(
        self,
        action: str,
        node_id: UUID | None = None,
        user: str | None = None,
        details: JsonObject | None = None,
    ) -> None:
        """Persist one audit result."""
        ...

    async def log_required(
        self,
        action: str,
        node_id: UUID | None = None,
        details: JsonObject | None = None,
    ) -> None:
        """Commit one audit intent before an external side effect."""
        ...
