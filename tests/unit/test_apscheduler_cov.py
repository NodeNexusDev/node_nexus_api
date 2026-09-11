"""Coverage tests for APScheduler runtime adapter (no live postgres/scheduler)."""

from __future__ import annotations

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

from app.adapters.runtime import apscheduler_runtime as rt_mod
from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime


def _pg_engine(conn=None):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    if conn is not None:
        engine.connect = AsyncMock(return_value=conn)
    else:
        engine.connect = AsyncMock()
    return engine


def _non_pg_engine():
    engine = MagicMock()
    engine.dialect.name = "sqlite"
    engine.connect = AsyncMock()
    return engine


def _ownership(*, acquired=False, postgres=True):
    own = MagicMock()
    own.is_acquired = acquired
    own.is_postgres = postgres
    own.try_acquire = AsyncMock(return_value=True)
    own.probe = AsyncMock(return_value=True)
    own.release = AsyncMock()
    return own


def test_configure_ownership_and_flags():
    r = ApschedulerRuntime()
    assert r.ready is False
    assert r.owns_execution is True
    own = _ownership(acquired=True)
    r.configure_ownership(own)
    assert r.owns_execution is True
    own.is_acquired = False
    assert r.owns_execution is False
    r.mark_restored(failed=0)
    assert r.ready is True
    r.mark_restored(failed=2)
    assert r.ready is False


def test_configure_executor_and_reconciler():
    r = ApschedulerRuntime()
    async def ex(a, b, c):
        return None
    async def rec():
        return (1, 0)
    r.configure_executor(ex)
    assert r._executor is ex
    r.configure_reconciler(rec)
    assert r._reconciler is rec


def test_record_misfire_event():
    r = ApschedulerRuntime()
    scheduled = datetime.now(UTC)
    r._record_scheduler_event(
        JobExecutionEvent(EVENT_JOB_MISSED, "j1", "default", scheduled)
    )


def test_record_execution_non_missed_returns():
    r = ApschedulerRuntime()
    scheduled = datetime.now(UTC)
    # JobExecutionEvent with a non-missed code falls through to second guard.
    r._record_scheduler_event(
        JobExecutionEvent(EVENT_JOB_MAX_INSTANCES, "j1", "default", scheduled)
    )


def test_record_generic_event_returns():
    r = ApschedulerRuntime()
    r._record_scheduler_event(MagicMock(spec=object()))


def test_record_overlap_event():
    r = ApschedulerRuntime()
    scheduled = datetime.now(UTC)
    r._record_scheduler_event(
        JobSubmissionEvent(EVENT_JOB_MAX_INSTANCES, "j1", "default", [scheduled])
    )


def test_start_reconciliation_noop_when_no_reconciler():
    r = ApschedulerRuntime()
    r.start_reconciliation(10.0)
    assert r._reconciliation_task is None


async def test_start_reconciliation_noop_when_task_exists():
    r = ApschedulerRuntime()
    r.configure_reconciler(AsyncMock(return_value=(0, 0)))
    r.start_reconciliation(3600)
    assert r._reconciliation_task is not None
    first = r._reconciliation_task
    r.start_reconciliation(3600)
    assert r._reconciliation_task is first
    await r.stop()


async def test_start_reconciliation_creates_task():
    r = ApschedulerRuntime()
    r.configure_reconciler(AsyncMock(return_value=(0, 0)))
    r.start_reconciliation(3600)
    assert r._reconciliation_task is not None
    await r.stop()


async def test_reconcile_loop_success():
    r = ApschedulerRuntime()
    r.configure_reconciler(AsyncMock(return_value=(2, 0)))
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._reconcile_loop(5)
    assert r.ready is True


async def test_reconcile_loop_no_reconciler_marks_degraded():
    r = ApschedulerRuntime()
    assert r._reconciler is None
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._reconcile_loop(5)
    assert r.ready is False


async def test_reconcile_loop_generic_error_marks_degraded():
    r = ApschedulerRuntime()
    r.configure_reconciler(AsyncMock(side_effect=RuntimeError("db")))
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._reconcile_loop(5)
    assert r.ready is False


async def test_reconcile_loop_cancelled_reraises():
    r = ApschedulerRuntime()
    r.configure_reconciler(AsyncMock(side_effect=asyncio.CancelledError))
    with patch.object(rt_mod.asyncio, "sleep", AsyncMock()) as slp:
        with pytest.raises(asyncio.CancelledError):
            await r._reconcile_loop(5)
    slp.assert_not_awaited()


async def test_start_when_not_running():
    r = ApschedulerRuntime()
    r._scheduler = MagicMock()
    r._scheduler.running = False
    await r.start()
    r._scheduler.start.assert_called_once()


async def test_start_when_already_running():
    r = ApschedulerRuntime()
    r._scheduler = MagicMock()
    r._scheduler.running = True
    await r.start()
    r._scheduler.start.assert_not_called()


async def test_acquire_ownership_via_port_true_and_false():
    r = ApschedulerRuntime()
    own = _ownership()
    own.try_acquire = AsyncMock(return_value=True)
    r.configure_ownership(own)
    assert await r.acquire_ownership() is True
    assert r._owns_execution is True
    own.try_acquire = AsyncMock(return_value=False)
    assert await r.acquire_ownership() is False
    assert r._owns_execution is False


async def test_acquire_ownership_legacy_no_engine():
    r = ApschedulerRuntime()
    assert await r.acquire_ownership(None) is True
    assert r._owns_execution is True


async def test_acquire_ownership_legacy_non_postgres():
    r = ApschedulerRuntime()
    assert await r.acquire_ownership(_non_pg_engine()) is True
    assert r._owns_execution is True


async def test_acquire_ownership_legacy_postgres_acquired():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.scalar.return_value = True
    engine = _pg_engine(conn)
    assert await r.acquire_ownership(engine) is True
    assert r._owns_execution is True
    assert r._owner_connection is conn
    await r.stop()


async def test_acquire_ownership_legacy_postgres_rejected():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.scalar.return_value = False
    engine = _pg_engine(conn)
    assert await r.acquire_ownership(engine) is False
    assert r._owns_execution is False
    conn.close.assert_awaited_once()


def test_start_ownership_monitor_port_not_postgres():
    r = ApschedulerRuntime()
    r.configure_ownership(_ownership(postgres=False))
    r.start_ownership_monitor()
    assert r._ownership_task is None


async def test_start_ownership_monitor_port_task_exists():
    r = ApschedulerRuntime()
    r.configure_ownership(_ownership(postgres=True, acquired=True))
    r.start_ownership_monitor()
    assert r._ownership_task is not None
    first = r._ownership_task
    r.start_ownership_monitor()
    assert r._ownership_task is first
    await r.stop()


async def test_start_ownership_monitor_port_creates_task():
    r = ApschedulerRuntime()
    r.configure_ownership(_ownership(postgres=True, acquired=True))
    r.start_ownership_monitor(None)
    assert r._ownership_task is not None
    await r.stop()


def test_start_ownership_monitor_legacy_noops():
    r = ApschedulerRuntime()
    r.start_ownership_monitor(None)
    assert r._ownership_task is None
    r.start_ownership_monitor(_non_pg_engine())
    assert r._ownership_task is None


async def test_start_ownership_monitor_legacy_task_exists():
    r = ApschedulerRuntime()
    engine = _pg_engine(AsyncMock())
    # Pre-seed a task so the second call is a noop.
    async def _never():
        await asyncio.sleep(3600)
    r._ownership_task = asyncio.create_task(_never())  # type: ignore[assignment]
    first = r._ownership_task
    r.start_ownership_monitor(engine)
    assert r._ownership_task is first
    assert isinstance(first, asyncio.Task)
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    r._ownership_task = None


async def test_start_ownership_monitor_legacy_creates_task():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.scalar.return_value = True
    engine = _pg_engine(conn)
    # Hold the lock so monitor goes to probe path (SELECT 1) instead of connect.
    r._owner_connection = conn
    r.start_ownership_monitor(engine)
    assert r._ownership_task is not None
    await r.stop()


async def test_monitor_ownership_with_port_no_ownership_raises():
    r = ApschedulerRuntime()
    with pytest.raises(RuntimeError, match="not configured"):
        await r._monitor_ownership_with_port()


async def test_monitor_port_acquires_when_not_acquired():
    r = ApschedulerRuntime()
    own = _ownership(acquired=False, postgres=True)
    own.try_acquire = AsyncMock(return_value=True)
    r.configure_ownership(own)
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership_with_port()
    own.try_acquire.assert_awaited()


async def test_monitor_port_probes_when_acquired():
    r = ApschedulerRuntime()
    own = _ownership(acquired=True, postgres=True)
    own.probe = AsyncMock(return_value=True)
    r.configure_ownership(own)
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership_with_port()
    own.probe.assert_awaited()
    assert r._owns_execution is True


async def test_monitor_port_probe_false_marks_lost():
    r = ApschedulerRuntime()
    own = _ownership(acquired=True, postgres=True)
    own.probe = AsyncMock(return_value=False)
    r.configure_ownership(own)
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership_with_port()
    assert r._owns_execution is False


async def test_monitor_port_probe_raises_marks_lost():
    r = ApschedulerRuntime()
    own = _ownership(acquired=True, postgres=True)
    own.probe = AsyncMock(side_effect=RuntimeError("db"))
    r.configure_ownership(own)
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership_with_port()
    assert r._owns_execution is False


async def test_monitor_port_cancelled_reraises():
    r = ApschedulerRuntime()
    own = _ownership(acquired=True, postgres=True)
    own.probe = AsyncMock(side_effect=asyncio.CancelledError)
    r.configure_ownership(own)
    with patch.object(rt_mod.asyncio, "sleep", AsyncMock()) as slp:
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership_with_port()
    slp.assert_not_awaited()


async def test_monitor_legacy_acquires_when_no_connection():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.scalar.return_value = True
    engine = _pg_engine(conn)
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership(engine)
    assert r._owns_execution is True
    await r.stop()


async def test_monitor_legacy_probes_existing_connection():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    r._owner_connection = conn
    engine = _pg_engine()
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership(engine)
    conn.execute.assert_awaited_once()
    assert r._owner_connection is conn
    r._owner_connection = None


async def test_monitor_legacy_execute_failure_closes():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("lost"))
    conn.close = AsyncMock()
    r._owner_connection = conn
    engine = _pg_engine()
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership(engine)
    assert r._owns_execution is False
    assert r._owner_connection is None
    conn.close.assert_awaited_once()


async def test_monitor_legacy_acquire_failure_no_connection():
    r = ApschedulerRuntime()
    engine = _pg_engine()
    engine.connect = AsyncMock(side_effect=RuntimeError("down"))
    with patch.object(
        rt_mod.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)
    ):
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership(engine)
    assert r._owns_execution is False
    assert r._owner_connection is None


async def test_monitor_legacy_cancelled_reraises():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=asyncio.CancelledError)
    r._owner_connection = conn
    with patch.object(rt_mod.asyncio, "sleep", AsyncMock()) as slp:
        with pytest.raises(asyncio.CancelledError):
            await r._monitor_ownership(_pg_engine())
    slp.assert_not_awaited()
    r._owner_connection = None


async def test_stop_cancels_tasks_and_shuts_down_scheduler():
    r = ApschedulerRuntime()
    r.configure_reconciler(AsyncMock(return_value=(0, 0)))
    r.start_reconciliation(3600)
    r.configure_ownership(_ownership(postgres=True, acquired=True))
    r.start_ownership_monitor()
    r._scheduler = MagicMock()
    r._scheduler.running = True
    await r.stop()
    assert r._reconciliation_task is None
    assert r._ownership_task is None
    r._scheduler.shutdown.assert_called_once()
    assert r.ready is False


async def test_stop_no_tasks_scheduler_not_running():
    r = ApschedulerRuntime()
    r._scheduler = MagicMock()
    r._scheduler.running = False
    await r.stop()
    r._scheduler.shutdown.assert_not_called()
    assert r._owns_execution is False


async def test_stop_ownership_release_failure_warns():
    r = ApschedulerRuntime()
    own = _ownership()
    own.release = AsyncMock(side_effect=RuntimeError("boom"))
    r.configure_ownership(own)
    r._scheduler = MagicMock()
    r._scheduler.running = False
    await r.stop()
    assert r._owns_execution is False


async def test_stop_legacy_unlock_and_close_ok():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.close = AsyncMock()
    r._owner_connection = conn
    r._scheduler = MagicMock()
    r._scheduler.running = False
    await r.stop()
    assert r._owner_connection is None
    assert r._owns_execution is False
    conn.execute.assert_awaited_once()
    conn.close.assert_awaited_once()


async def test_stop_legacy_unlock_failure_still_closes():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=RuntimeError("unlock"))
    conn.close = AsyncMock()
    r._owner_connection = conn
    r._scheduler = MagicMock()
    r._scheduler.running = False
    await r.stop()
    conn.close.assert_awaited_once()
    assert r._owner_connection is None


async def test_stop_legacy_close_failure():
    r = ApschedulerRuntime()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.close = AsyncMock(side_effect=RuntimeError("close"))
    r._owner_connection = conn
    r._scheduler = MagicMock()
    r._scheduler.running = False
    await r.stop()
    assert r._owner_connection is None


def test_schedule_script_default_and_replace():
    r = ApschedulerRuntime()
    sid = uuid4()
    nids = [uuid4()]
    jid = r.schedule_script(sid, "0 9 * * *", nids)
    assert jid == str(sid)
    # Replace existing triggers remove path.
    jid2 = r.schedule_script(
        sid, "0 18 * * *", nids, params={"a": 1}, timezone="UTC",
        misfire_grace_seconds=30, schedule_id=uuid4(),
    )
    assert jid2 == str(sid)
    assert r.get_schedule(sid) is not None


def test_schedule_script_custom_callback():
    r = ApschedulerRuntime()
    sid = uuid4()
    called: list[str] = []

    async def cb(script_id, node_ids, params):
        called.append(str(script_id))

    jid = r.schedule_script(sid, "* * * * *", [uuid4()], callback=cb)
    assert jid == str(sid)
    job = r._scheduler.get_job(jid)
    assert job is not None
    assert job.func is cb


async def test_execute_skipped_without_ownership():
    r = ApschedulerRuntime()
    ex = AsyncMock()
    r.configure_executor(ex)
    r._owns_execution = False
    await r._execute_scheduled_script(uuid4(), [uuid4()])
    ex.assert_not_awaited()


async def test_execute_missing_executor_raises():
    r = ApschedulerRuntime()
    with pytest.raises(RuntimeError, match="not configured"):
        await r._execute_scheduled_script(uuid4(), [uuid4()], {"k": "v"})


async def test_execute_success_and_failure():
    r = ApschedulerRuntime()
    ex = AsyncMock(return_value=None)
    r.configure_executor(ex)
    sid = uuid4()
    nids = [uuid4()]
    await r._execute_scheduled_script(sid, nids, {"x": 1})
    ex.assert_awaited_once_with(sid, nids, {"x": 1})
    r.configure_executor(AsyncMock(side_effect=ValueError("bad")))
    with pytest.raises(ValueError, match="bad"):
        await r._execute_scheduled_script(sid, nids)


async def test_execute_with_ownership_port_acquired():
    r = ApschedulerRuntime()
    own = _ownership(acquired=True)
    r.configure_ownership(own)
    ex = AsyncMock(return_value=None)
    r.configure_executor(ex)
    await r._execute_scheduled_script(uuid4(), [uuid4()])
    ex.assert_awaited_once()


def test_unschedule_found_and_missing():
    r = ApschedulerRuntime()
    sid = uuid4()
    assert r.unschedule_script(sid) is False
    r.schedule_script(sid, "0 9 * * *", [uuid4()])
    assert r.unschedule_script(sid) is True
    assert r.get_schedule(sid) is None


def test_get_schedule_shapes():
    r = ApschedulerRuntime()
    assert r.get_schedule(uuid4()) is None
    sid = uuid4()
    r.schedule_script(sid, "0 9 * * *", [])
    info = r.get_schedule(sid)
    assert info is not None
    assert info["script_id"] == str(sid)
    assert info["next_run_time"] is None
    job = r._scheduler.get_job(str(sid))
    job.next_run_time = datetime.now(UTC)
    info2 = r.get_schedule(sid)
    assert info2 is not None
    assert info2["next_run_time"] is not None


def test_get_next_run_time_branches():
    r = ApschedulerRuntime()
    assert r.get_next_run_time(uuid4()) is None
    sid = uuid4()
    r.schedule_script(sid, "0 9 * * *", [])
    # No next_run_time while scheduler is not started.
    assert r.get_next_run_time(sid) is None
    job = r._scheduler.get_job(str(sid))
    job.next_run_time = datetime.now(UTC)
    assert isinstance(r.get_next_run_time(sid), datetime)
    job.next_run_time = "not-a-datetime"  # type: ignore[assignment]
    assert r.get_next_run_time(sid) is None


def test_list_schedules_shapes():
    r = ApschedulerRuntime()
    assert r.list_schedules() == []
    s1 = uuid4()
    s2 = uuid4()
    r.schedule_script(s1, "0 9 * * *", [])
    r.schedule_script(s2, "0 10 * * *", [])
    job1 = r._scheduler.get_job(str(s1))
    job1.next_run_time = datetime.now(UTC)
    jobs = r.list_schedules()
    assert len(jobs) == 2
    by_id = {j["job_id"]: j for j in jobs}
    assert by_id[str(s1)]["next_run_time"] is not None
    assert by_id[str(s2)]["next_run_time"] is None
