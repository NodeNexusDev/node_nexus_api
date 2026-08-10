"""Application health probe ports."""

from typing import Protocol


class DatabaseHealthProbe(Protocol):
    """Probe database connectivity without exposing persistence details."""

    async def ping(self) -> tuple[bool, str]:
        """Return whether the database can answer a trivial query.

        The second tuple element is a human-readable detail string. It is safe
        to expose externally because it intentionally omits host/port.
        """
        ...
