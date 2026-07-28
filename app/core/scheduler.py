"""Scheduler configuration for cron-based script execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger()

ScheduledScriptExecutor = Callable[["UUID", list["UUID"]], Awaitable[None]]


class ScriptScheduler:
    """Application-scoped wrapper around the in-memory script scheduler."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, dict] = {}
        self._executor: ScheduledScriptExecutor | None = None

    def configure_executor(self, executor: ScheduledScriptExecutor) -> None:
        """Configure the application callback used by scheduled jobs."""
        self._executor = executor

    async def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("scheduler.started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
            logger.info("scheduler.stopped")

    def schedule_script(
        self,
        script_id: UUID,
        cron: str,
        node_ids: list[UUID],
        callback: object = None,
    ) -> str:
        """Schedule a script with a cron expression.

        Returns the job ID.
        """
        trigger = CronTrigger.from_crontab(cron)
        job_id = str(script_id)

        # Remove existing job if any
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

        cb = callback or self._execute_scheduled_script
        self._scheduler.add_job(
            cb,
            trigger,
            id=job_id,
            kwargs={"script_id": script_id, "node_ids": node_ids},
            replace_existing=True,
        )

        logger.info(
            "scheduler.script.scheduled",
            script_id=str(script_id),
            cron=cron,
            node_ids=[str(n) for n in node_ids],
        )
        return job_id

    async def _execute_scheduled_script(
        self, script_id: UUID, node_ids: list[UUID]
    ) -> None:
        """Execute a job through the callback configured by the composition root."""
        logger.info(
            "scheduler.script.executing",
            script_id=str(script_id),
            node_ids=[str(n) for n in node_ids],
        )
        if self._executor is None:
            raise RuntimeError("Scheduled script executor is not configured")
        await self._executor(script_id, node_ids)

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
        if job_id in self._jobs:
            self._jobs.pop(job_id)
            found = True
        if found:
            logger.info("scheduler.script.unscheduled", script_id=str(script_id))
        return found

    def get_schedule(self, script_id: UUID) -> dict | None:
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
        stored = self._jobs.get(job_id)
        if stored:
            return {
                "script_id": str(script_id),
                "cron": stored["cron"],
                "node_ids": stored["node_ids"],
            }
        return None

    def list_schedules(self) -> list[dict]:
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
