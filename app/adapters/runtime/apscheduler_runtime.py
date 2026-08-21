"""Concrete APScheduler lifecycle and ownership runtime."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog
from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
    JobSubmissionEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.metrics import (
    SCHEDULER_JOB_DURATION,
    SCHEDULER_JOBS,
    SCHEDULER_MISFIRES,
    SCHEDULER_OWNER,
    SCHEDULER_READY,
    SCHEDULER_SKIPPED_OVERLAP,
    SCHEDULER_START_LAG,
)

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

ScheduledScriptExecutor = Callable[
    ["UUID", list["UUID"], dict[str, Any]], Awaitable[None]
]
ScheduleReconciler = Callable[[], Awaitable[tuple[int, int]]]
_SCHEDULER_LOCK_ID = 5_642_395_847_322_111
_DEFAULT_OWNERSHIP_POLL_SECONDS = 5.0


class ApschedulerRuntime:
    """Application-scoped APScheduler engine and ownership manager."""

    def __init__(
        self,
        *,
        ownership_poll_seconds: float = _DEFAULT_OWNERSHIP_POLL_SECONDS,
    ) -> None:
        self._ownership_poll_seconds = ownership_poll_seconds
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_listener(
            self._record_scheduler_event,
            EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES,
        )
        self._executor: ScheduledScriptExecutor | None = None
        self._owner_connection: AsyncConnection | None = None
        self._owns_execution = True
        self._ownership_task: asyncio.Task[None] | None = None
        self._reconciliation_task: asyncio.Task[None] | None = None
        self._reconciler: ScheduleReconciler | None = None
        self._ready = False

    @staticmethod
    def _record_scheduler_event(
        event: JobExecutionEvent | JobSubmissionEvent,
    ) -> None:
        """Record APScheduler misfire and overlap decisions."""
        if isinstance(event, JobExecutionEvent) and event.code == EVENT_JOB_MISSED:
            SCHEDULER_MISFIRES.inc()
            scheduled_run_time = event.scheduled_run_time
            lag = max(
                0.0,
                (
                    datetime.now(scheduled_run_time.tzinfo) - scheduled_run_time
                ).total_seconds(),
            )
            SCHEDULER_START_LAG.observe(lag)
            logger.warning("scheduler.job.misfired", job_id=event.job_id, lag=lag)
            return
        if not isinstance(event, JobSubmissionEvent):
            return
        SCHEDULER_SKIPPED_OVERLAP.inc()
        logger.warning(
            "scheduler.job.skipped_overlap",
            job_id=event.job_id,
            skipped_runs=len(event.scheduled_run_times),
        )

    def configure_executor(self, executor: ScheduledScriptExecutor) -> None:
        """Configure the application callback used by scheduled jobs."""
        self._executor = executor

    def configure_reconciler(self, reconciler: ScheduleReconciler) -> None:
        """Configure persistent-to-runtime reconciliation."""
        self._reconciler = reconciler

    @property
    def ready(self) -> bool:
        """Return whether persistent schedules have been restored successfully."""
        return self._ready

    @property
    def owns_execution(self) -> bool:
        """Return whether this replica owns scheduled execution."""
        return self._owns_execution

    def mark_restored(self, *, failed: int) -> None:
        """Publish restoration readiness."""
        self._ready = failed == 0
        SCHEDULER_READY.set(1 if self._ready else 0)

    def start_reconciliation(self, interval_seconds: float = 10.0) -> None:
        """Continuously repair the runtime projection."""
        if self._reconciler is not None and self._reconciliation_task is None:
            self._reconciliation_task = asyncio.create_task(
                self._reconcile_loop(interval_seconds)
            )

    async def _reconcile_loop(self, interval_seconds: float) -> None:
        while True:
            try:
                reconciler = self._reconciler
                if reconciler is None:
                    raise RuntimeError("Scheduler reconciler is not configured")
                restored, failed = await reconciler()
                self.mark_restored(failed=failed)
                logger.info(
                    "scheduler.reconcile.completed",
                    restored=restored,
                    failed=failed,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.mark_restored(failed=1)
                logger.exception(
                    "scheduler.reconcile.failed",
                    error_type=type(exc).__name__,
                )
            await asyncio.sleep(interval_seconds)

    async def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("scheduler.started")

    async def acquire_ownership(self, engine: AsyncEngine) -> bool:
        """Acquire the PostgreSQL session advisory lock for this replica."""
        self._owns_execution = False
        SCHEDULER_OWNER.set(0)
        if engine.dialect.name != "postgresql":
            self._owns_execution = True
            SCHEDULER_OWNER.set(1)
            return True
        connection = await engine.connect()
        acquired = bool(
            await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": _SCHEDULER_LOCK_ID},
            )
        )
        if not acquired:
            await connection.close()
            logger.info("scheduler.owner.rejected")
            return False
        self._owner_connection = connection
        self._owns_execution = True
        SCHEDULER_OWNER.set(1)
        logger.info("scheduler.owner.acquired")
        return True

    def start_ownership_monitor(self, engine: AsyncEngine) -> None:
        """Continuously acquire ownership after startup or owner failover."""
        if engine.dialect.name != "postgresql" or self._ownership_task is not None:
            return
        self._ownership_task = asyncio.create_task(self._monitor_ownership(engine))

    async def _monitor_ownership(self, engine: AsyncEngine) -> None:
        """Maintain a live advisory-lock session and retry after loss."""
        while True:
            try:
                if self._owner_connection is None:
                    await self.acquire_ownership(engine)
                else:
                    await self._owner_connection.execute(text("SELECT 1"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "scheduler.owner.lost",
                    error_type=type(exc).__name__,
                )
                self._owns_execution = False
                SCHEDULER_OWNER.set(0)
                if self._owner_connection is not None:
                    await self._owner_connection.close()
                    self._owner_connection = None
            await asyncio.sleep(self._ownership_poll_seconds)

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._reconciliation_task is not None:
            self._reconciliation_task.cancel()
            await asyncio.gather(self._reconciliation_task, return_exceptions=True)
            self._reconciliation_task = None
        if self._ownership_task is not None:
            self._ownership_task.cancel()
            await asyncio.gather(self._ownership_task, return_exceptions=True)
            self._ownership_task = None
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
            logger.info("scheduler.stopped")
        if self._owner_connection is not None:
            await self._owner_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": _SCHEDULER_LOCK_ID},
            )
            await self._owner_connection.close()
            self._owner_connection = None
        self._owns_execution = False
        self._ready = False
        SCHEDULER_OWNER.set(0)
        SCHEDULER_READY.set(0)

    def schedule_script(
        self,
        script_id: UUID,
        cron: str,
        node_ids: list[UUID],
        callback: object = None,
        *,
        params: dict[str, Any] | None = None,
        timezone: str = "UTC",
        misfire_grace_seconds: int = 60,
        schedule_id: UUID | None = None,
    ) -> str:
        """Schedule a script with a cron expression.

        Returns the job ID.
        """
        trigger = CronTrigger.from_crontab(cron, timezone=ZoneInfo(timezone))
        job_id = str(script_id)

        # Remove existing job if any
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        cb = callback or self._execute_scheduled_script
        self._scheduler.add_job(
            cb,
            trigger,
            id=job_id,
            kwargs={
                "script_id": script_id,
                "node_ids": node_ids,
                "params": params or {},
            },
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=misfire_grace_seconds,
        )

        logger.info(
            "scheduler.script.scheduled",
            script_id=str(script_id),
            schedule_id=str(schedule_id) if schedule_id else None,
            timezone=timezone,
            target_count=len(node_ids),
        )
        return job_id

    async def _execute_scheduled_script(
        self,
        script_id: UUID,
        node_ids: list[UUID],
        params: dict[str, Any] | None = None,
    ) -> None:
        """Execute a job through the callback configured by the composition root."""
        if not self._owns_execution:
            logger.warning(
                "scheduler.job.skipped_no_ownership",
                script_id=str(script_id),
            )
            return
        logger.info(
            "scheduler.script.executing",
            script_id=str(script_id),
            target_count=len(node_ids),
        )
        if self._executor is None:
            raise RuntimeError("Scheduled script executor is not configured")
        started = time.monotonic()
        SCHEDULER_JOBS.labels(outcome="started").inc()
        try:
            await self._executor(script_id, node_ids, params or {})
        except Exception:
            SCHEDULER_JOBS.labels(outcome="failed").inc()
            raise
        else:
            SCHEDULER_JOBS.labels(outcome="succeeded").inc()
        finally:
            SCHEDULER_JOB_DURATION.observe(time.monotonic() - started)

    def unschedule_script(self, script_id: UUID) -> bool:
        """Remove a scheduled script.

        Returns True if the job was found and removed.
        """
        job_id = str(script_id)
        found = False
        job = self._scheduler.get_job(job_id)
        if job:
            self._scheduler.remove_job(job_id)
            found = True
        if found:
            logger.info("scheduler.script.unscheduled", script_id=str(script_id))
        return found

    def get_schedule(self, script_id: UUID) -> dict[str, Any] | None:
        """Get schedule info for a script."""
        job_id = str(script_id)
        job = self._scheduler.get_job(job_id)
        if job:
            next_run = getattr(job, "next_run_time", None)
            return {
                "script_id": str(script_id),
                "cron": str(job.trigger),
                "next_run_time": str(next_run) if next_run else None,
            }
        return None

    def get_next_run_time(self, script_id: UUID) -> datetime | None:
        """Return APScheduler's timezone-aware next run timestamp."""
        job = self._scheduler.get_job(str(script_id))
        value = getattr(job, "next_run_time", None) if job else None
        return value if isinstance(value, datetime) else None

    def list_schedules(self) -> list[dict[str, Any]]:
        """List all scheduled jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            jobs.append(
                {
                    "job_id": job.id,
                    "cron": str(job.trigger),
                    "next_run_time": str(next_run) if next_run else None,
                }
            )
        return jobs
