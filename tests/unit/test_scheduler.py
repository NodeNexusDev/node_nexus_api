"""Tests for script scheduler."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from apscheduler.events import (
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
    JobSubmissionEvent,
)

from app.core.scheduler import ScriptScheduler
from app.schemas.scheduler import ScheduledJob, ScheduleRequest, ScheduleResponse


class TestScriptScheduler:
    """Tests for ScriptScheduler."""

    def test_schedule_script(self):
        """Schedule a script with cron expression."""
        scheduler = ScriptScheduler()
        script_id = uuid4()
        node_ids = [uuid4()]

        job_id = scheduler.schedule_script(script_id, "0 9 * * *", node_ids)

        assert job_id == str(script_id)
        info = scheduler.get_schedule(script_id)
        assert info is not None
        assert "cron" in info

    def test_unschedule_script(self):
        """Unschedule a script removes it."""
        scheduler = ScriptScheduler()
        script_id = uuid4()
        scheduler.schedule_script(script_id, "0 9 * * *", [uuid4()])

        removed = scheduler.unschedule_script(script_id)
        assert removed is True
        assert scheduler.get_schedule(script_id) is None

    def test_unschedule_nonexistent(self):
        """Unschedule non-existent script returns False."""
        scheduler = ScriptScheduler()
        removed = scheduler.unschedule_script(uuid4())
        assert removed is False

    def test_get_schedule_nonexistent(self):
        """Get schedule for non-existent script returns None."""
        scheduler = ScriptScheduler()
        info = scheduler.get_schedule(uuid4())
        assert info is None

    def test_replace_existing_schedule(self):
        """Scheduling same script twice replaces the first."""
        scheduler = ScriptScheduler()
        script_id = uuid4()
        node_ids = [uuid4()]

        scheduler.schedule_script(script_id, "0 9 * * *", node_ids)
        scheduler.schedule_script(script_id, "0 18 * * *", node_ids)

        info = scheduler.get_schedule(script_id)
        assert info is not None
        # The cron should be updated
        assert "cron" in info

    def test_list_schedules_empty(self):
        """List schedules when empty."""
        scheduler = ScriptScheduler()
        jobs = scheduler.list_schedules()
        assert jobs == []

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Scheduler can be started and stopped."""
        scheduler = ScriptScheduler()
        await scheduler.start()
        assert scheduler._scheduler.running
        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_configured_executor_runs_job(self):
        """Default job callback delegates to the configured executor."""
        script_id = uuid4()
        node_ids = [uuid4()]
        calls: list[tuple[object, object, object]] = []

        async def executor(received_script_id, received_node_ids, received_params):
            calls.append((received_script_id, received_node_ids, received_params))

        scheduler = ScriptScheduler()
        scheduler.configure_executor(executor)

        await scheduler._execute_scheduled_script(script_id, node_ids)

        assert calls == [(script_id, node_ids, {})]

    @pytest.mark.asyncio
    async def test_missing_executor_is_explicit(self):
        """Executing a scheduled job without composition setup fails clearly."""
        scheduler = ScriptScheduler()

        with pytest.raises(
            RuntimeError, match="Scheduled script executor is not configured"
        ):
            await scheduler._execute_scheduled_script(uuid4(), [uuid4()])

    async def test_postgresql_ownership_lock_is_acquired_and_released(self):
        scheduler = ScriptScheduler()
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        connection = AsyncMock()
        connection.scalar.return_value = True
        engine.connect = AsyncMock(return_value=connection)

        assert await scheduler.acquire_ownership(engine) is True
        assert scheduler._owns_execution is True
        await scheduler.stop()

        connection.execute.assert_awaited_once()
        connection.close.assert_awaited_once()

    async def test_postgresql_ownership_rejection_closes_connection(self):
        scheduler = ScriptScheduler()
        engine = MagicMock()
        engine.dialect.name = "postgresql"
        connection = AsyncMock()
        connection.scalar.return_value = False
        engine.connect = AsyncMock(return_value=connection)

        assert await scheduler.acquire_ownership(engine) is False
        assert scheduler._owns_execution is False
        connection.close.assert_awaited_once()

    async def test_reconciliation_updates_readiness(self):
        scheduler = ScriptScheduler()
        scheduler.configure_reconciler(AsyncMock(return_value=(2, 0)))
        with patch(
            "app.core.scheduler.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await scheduler._reconcile_loop(0)
        assert scheduler.ready is True

    async def test_reconciliation_failure_sets_degraded(self):
        scheduler = ScriptScheduler()
        scheduler.configure_reconciler(AsyncMock(side_effect=RuntimeError("db")))
        with patch(
            "app.core.scheduler.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await scheduler._reconcile_loop(0)
        assert scheduler.ready is False

    async def test_stop_cancels_reconciliation_task(self):
        scheduler = ScriptScheduler()
        scheduler.configure_reconciler(AsyncMock(return_value=(0, 0)))
        scheduler.start_reconciliation(3600)
        assert scheduler._reconciliation_task is not None
        await scheduler.stop()
        assert scheduler._reconciliation_task is None

    async def test_ownership_monitor_recovers_lost_connection(self):
        scheduler = ScriptScheduler()
        connection = AsyncMock()
        connection.execute.side_effect = RuntimeError("lost")
        scheduler._owner_connection = connection
        engine = MagicMock()
        with patch(
            "app.core.scheduler.asyncio.sleep",
            AsyncMock(side_effect=asyncio.CancelledError),
        ):
            with pytest.raises(asyncio.CancelledError):
                await scheduler._monitor_ownership(engine)
        assert scheduler.owns_execution is False
        assert scheduler._owner_connection is None

    async def test_job_is_skipped_without_ownership(self):
        scheduler = ScriptScheduler()
        executor = AsyncMock()
        scheduler.configure_executor(executor)
        scheduler._owns_execution = False
        await scheduler._execute_scheduled_script(uuid4(), [uuid4()])
        executor.assert_not_awaited()

    async def test_job_failure_is_propagated(self):
        scheduler = ScriptScheduler()
        scheduler.configure_executor(AsyncMock(side_effect=ValueError("failed")))
        with pytest.raises(ValueError, match="failed"):
            await scheduler._execute_scheduled_script(uuid4(), [uuid4()])

    def test_next_run_time(self):
        scheduler = ScriptScheduler()
        script_id = uuid4()
        scheduler.schedule_script(script_id, "0 9 * * *", [])
        assert scheduler.get_next_run_time(script_id) is None
        job = scheduler._scheduler.get_job(str(script_id))
        job.next_run_time = datetime.now(UTC)
        assert scheduler.get_next_run_time(script_id) is not None

    def test_records_misfire_and_overlap_events(self):
        scheduler = ScriptScheduler()
        scheduled = datetime.now(UTC)
        scheduler._record_scheduler_event(
            JobExecutionEvent(
                EVENT_JOB_MISSED,
                "job",
                "default",
                scheduled,
            )
        )
        scheduler._record_scheduler_event(
            JobSubmissionEvent(
                EVENT_JOB_MAX_INSTANCES,
                "job",
                "default",
                [scheduled],
            )
        )


class TestSchedulerSchemas:
    """Tests for scheduler schemas."""

    def test_schedule_request(self):
        """ScheduleRequest validates correctly."""
        req = ScheduleRequest(cron="0 9 * * *", node_ids=[uuid4()])
        assert req.cron == "0 9 * * *"
        assert len(req.node_ids) == 1

    def test_schedule_response(self):
        """ScheduleResponse has correct defaults."""
        resp = ScheduleResponse(script_id="abc", cron="0 9 * * *")
        assert resp.message == "Script scheduled successfully"

    def test_scheduled_job(self):
        """ScheduledJob schema."""
        job = ScheduledJob(
            id=uuid4(),
            script_id=uuid4(),
            cron="0 9 * * *",
            timezone="UTC",
            node_ids=[],
            params={},
            enabled=True,
            misfire_grace_seconds=60,
            operational_state="registered",
        )
        assert job.timezone == "UTC"
