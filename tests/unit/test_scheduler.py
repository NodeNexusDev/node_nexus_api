"""Tests for script scheduler."""

from uuid import uuid4

import pytest

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
        calls: list[tuple[object, object]] = []

        async def executor(received_script_id, received_node_ids):
            calls.append((received_script_id, received_node_ids))

        scheduler = ScriptScheduler()
        scheduler.configure_executor(executor)

        await scheduler._execute_scheduled_script(script_id, node_ids)

        assert calls == [(script_id, node_ids)]

    @pytest.mark.asyncio
    async def test_missing_executor_is_explicit(self):
        """Executing a scheduled job without composition setup fails clearly."""
        scheduler = ScriptScheduler()

        with pytest.raises(
            RuntimeError, match="Scheduled script executor is not configured"
        ):
            await scheduler._execute_scheduled_script(uuid4(), [uuid4()])


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
            script_id="abc",
            cron="0 9 * * *",
            next_run_time="2026-01-01T09:00:00",
        )
        assert job.script_id == "abc"
