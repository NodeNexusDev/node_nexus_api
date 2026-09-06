"""PostgreSQL advisory-lock ownership persistence adapter."""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = structlog.get_logger()

_SCHEDULER_LOCK_ID = 5_642_395_847_322_111


class SqlAlchemySchedulerOwnership:
    """Manage the global scheduler advisory lock via SQLAlchemy."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._connection: AsyncConnection | None = None
        self._acquired = False

    @property
    def is_acquired(self) -> bool:
        return self._acquired

    @property
    def is_postgres(self) -> bool:
        return self._engine.dialect.name == "postgresql"

    async def try_acquire(self) -> bool:
        """Try to acquire the lock."""
        if not self.is_postgres:
            self._acquired = True
            return True
        if self._acquired and self._connection is not None:
            return True
        conn = await self._engine.connect()
        try:
            acquired = bool(
                await conn.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": _SCHEDULER_LOCK_ID},
                )
            )
        except Exception:
            await conn.close()
            raise
        if not acquired:
            await conn.close()
            self._acquired = False
            logger.info("scheduler.owner.rejected")
            return False
        self._connection = conn
        self._acquired = True
        logger.info("scheduler.owner.acquired")
        return True

    async def probe(self) -> bool:
        """Return True if lock connection is alive."""
        if not self.is_postgres:
            return True
        if self._connection is None:
            return False
        try:
            await self._connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def release(self) -> None:
        """Release the lock if held."""
        if not self.is_postgres:
            self._acquired = False
            return
        if self._connection is not None:
            try:
                await self._connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _SCHEDULER_LOCK_ID},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler.owner.unlock_failed", error=str(exc))
            try:
                await self._connection.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler.owner.close_failed", error=str(exc))
            self._connection = None
        self._acquired = False
