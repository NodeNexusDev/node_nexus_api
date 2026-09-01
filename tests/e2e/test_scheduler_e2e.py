"""Full-stack scheduler execution, recovery, and failover scenarios."""

import asyncio
import time
from uuid import UUID

import asyncpg
import httpx2 as httpx
import pytest

from app.adapters.runtime.apscheduler_runtime import _SCHEDULER_LOCK_ID
from tests.e2e.helpers.polling import wait_for_condition
from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController
from tests.types import UnvalidatedJsonObject

pytestmark = [pytest.mark.docker, pytest.mark.e2e_scheduler]


def _wait_for_api(client: httpx.Client, *, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get("/ready")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    pytest.fail("API did not become ready after restart")


def _wait_for_execution(
    client: httpx.Client,
    script_id: str,
    *,
    timeout: float = 10.0,
) -> list[UnvalidatedJsonObject]:
    def _has_execution() -> bool:
        response = client.get(f"/api/v2/scripts/{script_id}/executions")
        return bool(response.status_code == 200 and response.json()["total"] > 0)

    wait_for_condition(
        _has_execution,
        timeout=timeout,
        pause=0.2,
        description="scheduled execution to appear",
    )
    return client.get(f"/api/v2/scripts/{script_id}/executions").json()["items"]


def _wait_for_completed_execution(
    client: httpx.Client,
    script_id: str,
    *,
    timeout: float = 10.0,
) -> list[UnvalidatedJsonObject]:
    def _is_completed() -> bool:
        response = client.get(f"/api/v2/scripts/{script_id}/executions")
        if response.status_code != 200 or response.json()["total"] == 0:
            return False
        return response.json()["items"][0]["status"] in ("success", "error")

    wait_for_condition(
        _is_completed,
        timeout=timeout,
        pause=0.2,
        description="scheduled execution to complete",
    )
    return client.get(f"/api/v2/scripts/{script_id}/executions").json()["items"]


def _schedule_url(script_id: str) -> str:
    return f"/api/v2/scripts/{script_id}/schedule"


def _executions_url(script_id: str) -> str:
    return f"/api/v2/scripts/{script_id}/executions"


async def _lock_held_by_another(
    connection: asyncpg.Connection,
    lock_id: int = _SCHEDULER_LOCK_ID,
) -> bool:
    """Return True if another session holds the advisory lock.

    Uses a transaction-scoped lock so the test connection never keeps it.
    """
    acquired = await connection.fetchval(
        "SELECT pg_try_advisory_xact_lock($1)", lock_id
    )
    return not acquired


async def _wait_lock_held_by_another(
    connection: asyncpg.Connection,
    *,
    timeout: float = 10.0,
) -> None:
    """Wait until another session holds the scheduler advisory lock."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await _lock_held_by_another(connection):
            return
        await asyncio.sleep(0.5)
    raise AssertionError(
        f"Scheduler lock was not held by another session within {timeout}s"
    )


def test_reconciliation_restores_schedule_after_restart(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    docker_service_controller: DockerServiceController,
) -> None:
    """Reconciliation loop restores runtime projection from persistent schedule.

    Verifies the full lifecycle:
    1. Schedule is registered with operational_state=registered.
    2. API restart clears all in-memory scheduler state.
    3. Reconciliation restores the schedule from DB.
    4. Schedule executes exactly once when triggered via the E2E harness.

    A far-future cron is used so the test does not depend on wall-clock
    minute boundaries between restore and trigger-now.
    """
    node = e2e_resources.create_ssh_node()
    script = e2e_resources.create_script(
        steps=[
            {
                "label": "reconcile",
                "type": "inline",
                "command": "echo reconciliation-ok",
            }
        ]
    )
    e2e_resources.create_schedule(script["id"], [node["id"]], cron="0 9 * * *")

    # Verify initial state
    resp = e2e_client.get(_schedule_url(script["id"]))
    assert resp.status_code == 200
    initial = resp.json()
    assert initial["enabled"] is True
    assert initial["operational_state"] == "registered"
    assert initial["cron"] == "0 9 * * *"

    # Clear runtime state by restarting API
    docker_service_controller.restart("api")
    _wait_for_api(e2e_client)

    # Reconciliation should restore the schedule
    resp = e2e_client.get(_schedule_url(script["id"]))
    assert resp.status_code == 200
    restored = resp.json()
    assert restored["enabled"] is True
    assert restored["operational_state"] == "registered"
    assert restored["cron"] == "0 9 * * *"
    assert restored["next_run_at"] is not None

    # Trigger execution immediately via the E2E harness.
    resp = e2e_client.post(f"/api/v2/internal/e2e/scheduler/{script['id']}/trigger-now")
    assert resp.status_code == 200
    assert resp.json()["status"] == "triggered"

    # Verify exactly one execution (no duplicates from reconciliation)
    executions = _wait_for_completed_execution(e2e_client, script["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "success"
    assert executions[0]["started_at"] is not None
    assert executions[0]["finished_at"] is not None
    assert executions[0]["steps"][0]["exit_code"] == 0
    assert "reconciliation-ok" in executions[0]["steps"][0]["stdout"]

    # Confirm no duplicate execution
    final_resp = e2e_client.get(_executions_url(script["id"]))
    assert final_resp.json()["total"] == 1

    # Verify schedule metadata after execution
    resp = e2e_client.get(_schedule_url(script["id"]))
    assert resp.status_code == 200
    final_schedule = resp.json()
    assert final_schedule["last_run_at"] is not None
    assert final_schedule["last_success_at"] is not None
    assert final_schedule["next_run_at"] is not None
    assert final_schedule["last_error_type"] is None


def test_schedule_replace_removes_old_runtime_job(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Replacing a schedule with a new cron removes the old runtime job.

    The new cron should be the only active one. We verify by checking that
    only one execution appears and it matches the new schedule.
    """
    node = e2e_resources.create_ssh_node()
    script = e2e_resources.create_script(
        steps=[
            {
                "label": "replace",
                "type": "inline",
                "command": "echo replace-ok",
            }
        ]
    )

    # First schedule with a far-future cron (should never fire)
    resp = e2e_client.post(
        _schedule_url(script["id"]),
        json={"cron": "0 0 31 12 *", "node_ids": [node["id"]]},
    )
    assert resp.status_code == 200
    assert resp.json()["cron"] == "0 0 31 12 *"

    # Replace with per-minute cron
    resp = e2e_client.post(
        _schedule_url(script["id"]),
        json={"cron": "* * * * *", "node_ids": [node["id"]]},
    )
    assert resp.status_code == 200
    assert resp.json()["cron"] == "* * * * *"

    # Verify the far-future cron is gone
    resp = e2e_client.get(_schedule_url(script["id"]))
    assert resp.status_code == 200
    schedule = resp.json()
    assert schedule["cron"] == "* * * * *"
    assert schedule["next_run_at"] is not None

    # Trigger execution immediately and verify only one run occurs.
    resp = e2e_client.post(f"/api/v2/internal/e2e/scheduler/{script['id']}/trigger-now")
    assert resp.status_code == 200

    executions = _wait_for_completed_execution(e2e_client, script["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "success"
    assert "replace-ok" in executions[0]["steps"][0]["stdout"]

    # No duplicate executions from the old far-future cron.
    final = e2e_client.get(_executions_url(script["id"])).json()
    assert final["total"] == 1


def test_persistent_schedule_recovers_after_api_restart(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    docker_service_controller: DockerServiceController,
) -> None:
    """An empty runtime projection is restored from the persistent schedule.

    Execution is triggered through the E2E harness. A far-future cron avoids
    a race with the minute boundary between restore and trigger-now.
    """
    node = e2e_resources.create_ssh_node()
    script = e2e_resources.create_script(
        steps=[
            {
                "label": "restart",
                "type": "inline",
                "command": "echo scheduler-restart-ok",
            }
        ]
    )
    schedule = e2e_resources.create_schedule(
        script["id"], [node["id"]], cron="0 9 * * *"
    )
    assert schedule["cron"] == "0 9 * * *"

    docker_service_controller.restart("api")
    _wait_for_api(e2e_client)

    restored = e2e_client.get(_schedule_url(script["id"]))
    assert restored.status_code == 200, restored.text
    restored_schedule = restored.json()
    assert restored_schedule["enabled"] is True
    assert restored_schedule["cron"] == "0 9 * * *"
    assert restored_schedule["next_run_at"] is not None

    resp = e2e_client.post(f"/api/v2/internal/e2e/scheduler/{script['id']}/trigger-now")
    assert resp.status_code == 200

    executions = _wait_for_execution(e2e_client, script["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "success"
    assert "scheduler-restart-ok" in executions[0]["steps"][0]["stdout"]


@pytest.mark.asyncio
async def test_scheduler_replica_failover_has_no_duplicate_execution(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    postgres_connection: asyncpg.Connection,
    docker_service_controller: DockerServiceController,
    service_ports: object,
) -> None:
    """A contender takes the advisory lock and executes a durable job once."""
    del service_ports  # Ensures the full stack is ready before replica operations.
    docker_service_controller.start("api-replica")
    api_stopped = False
    try:
        node = e2e_resources.create_ssh_node()
        script = e2e_resources.create_script(
            steps=[
                {
                    "label": "failover",
                    "type": "inline",
                    "command": "echo scheduler-failover-ok",
                }
            ]
        )
        # Use a per-minute cron; the primary API currently owns the lock.
        e2e_resources.create_schedule(script["id"], [node["id"]], cron="* * * * *")

        # Verify the primary API holds the lock (replica is rejected).
        await _wait_lock_held_by_another(postgres_connection, timeout=10.0)

        docker_service_controller.stop("api")
        api_stopped = True

        # Wait for the replica to take over the advisory lock.
        await _wait_lock_held_by_another(postgres_connection, timeout=30.0)

        # Wait for the replica to execute the scheduled job.
        execution_count = 0
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            execution_count = await postgres_connection.fetchval(
                "SELECT count(*) FROM script_executions WHERE script_id = $1",
                UUID(script["id"]),
            )
            if execution_count:
                break
            await asyncio.sleep(1)
        assert execution_count == 1

        # Wait for execution count to remain at 1 (no duplicates)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            count = await postgres_connection.fetchval(
                "SELECT count(*) FROM script_executions WHERE script_id = $1",
                UUID(script["id"]),
            )
            assert count == 1
            time.sleep(0.5)

        docker_service_controller.start("api")
        api_stopped = False
        _wait_for_api(e2e_client)

        # Wait for primary to come back and be rejected by replica
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if await _lock_held_by_another(postgres_connection):
                break
            time.sleep(1)

        assert await _lock_held_by_another(postgres_connection)
        assert (
            await postgres_connection.fetchval(
                "SELECT count(*) FROM script_executions WHERE script_id = $1",
                UUID(script["id"]),
            )
            == 1
        )
    finally:
        if api_stopped:
            docker_service_controller.start("api")
            _wait_for_api(e2e_client)
        docker_service_controller.stop("api-replica")
