"""Application health probe ports."""

from typing import Protocol


class DatabaseHealthProbe(Protocol):
    """Probe database connectivity without exposing persistence details."""

    async def ping(self) -> bool:
        """Return whether the database can answer a trivial query."""
        ...
