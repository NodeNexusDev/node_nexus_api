"""Port for distributed scheduler ownership (advisory lock)."""

from __future__ import annotations

from typing import Protocol


class SchedulerOwnership(Protocol):
    """Abstract PostgreSQL advisory-lock ownership."""

    async def try_acquire(self) -> bool:
        """Try to acquire the global scheduler lock. Return True if acquired."""
        ...

    async def release(self) -> None:
        """Release the lock if held."""
        ...

    async def probe(self) -> bool:
        """Probe that the lock-holding connection is still alive. Return True if ok."""
        ...

    @property
    def is_acquired(self) -> bool:
        """Whether this replica currently holds the lock."""
        ...

    @property
    def is_postgres(self) -> bool:
        """True for PostgreSQL engines, False for SQLite/tests (auto-acquired)."""
        ...
