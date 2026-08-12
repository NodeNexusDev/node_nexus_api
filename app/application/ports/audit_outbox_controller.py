"""Application port for audit outbox lifecycle control."""

from typing import Protocol


class AuditOutboxController(Protocol):
    """Start or stop background audit-outbox delivery."""

    def start(self) -> None: ...

    async def stop(self) -> None: ...
