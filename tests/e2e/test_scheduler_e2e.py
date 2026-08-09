"""Full-stack scheduler execution, recovery, and failover scenarios."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController

pytestmark = pytest.mark.docker


def _next_minute_cron() -> tuple[str, datetime]:
    """Return a UTC cron safely ahead of the current minute boundary."""
    now = datetime.now(UTC)
    minutes = 2 if now.second >= 45 else 1
    run_at = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    return f"{run_at.minute} {run_at.hour} * * *", run_at


def _wait_for_api(client: httpx.Client, *, timeout: float = 120.0) -> None:
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
    timeout: float = 130.0,
) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/scripts/{script_id}/executions")
        if response.status_code == 200 and response.json()["total"] > 0:
            return response.json()["items"]
        time.sleep(1)
    pytest.fail("Scheduled execution did not appear before the deadline")


def _wait_for_completed_execution(
    client: httpx.Client,
    script_id: str,
    *,
    timeout: float = 130.0,
) -> list[dict]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/scripts/{script_id}/executions")
        if response.status_code == 200 and response.json()["total"] > 0:
            items = response.json()["items"]
            if items[0]["status"] in ("completed", "failed"):
                return items
        time.sleep(1)
    pytest.fail("Scheduled execution did not complete before the deadline")


def _schedule_url(script_id: str) -> str:
    return f"/api/v1/scripts/{script_id}/schedule"


def _executions_url(script_id: str) -> str:
    return f"/api/v1/scripts/{script_id}/executions"


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
    4. Schedule executes exactly once after reconciliation.
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
    cron, run_at = _next_minute_cron()
    e2e_resources.create_schedule(script["id"], [node["id"]], cron=cron)

    # Verify initial state
    resp = e2e_client.get(_schedule_url(script["id"]))
    assert resp.status_code == 200
    initial = resp.json()
    assert initial["enabled"] is True
    assert initial["operational_state"] == "registered"
    assert initial["cron"] == cron

    # Clear runtime state by restarting API
    docker_service_controller.restart("api")
    _wait_for_api(e2e_client)

    # Reconciliation should restore the schedule
    resp = e2e_client.get(_schedule_url(script["id"]))
    assert resp.status_code == 200
    restored = resp.json()
    assert restored["enabled"] is True
    assert restored["operational_state"] == "registered"
    assert restored["cron"] == cron
    assert restored["next_run_at"] is not None

    # Verify exactly one execution (no duplicates from reconciliation)
    executions = _wait_for_completed_execution(e2e_client, script["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "completed"
    assert executions[0]["started_at"] is not None
    assert executions[0]["finished_at"] is not None
    assert executions[0]["steps"][0]["exit_code"] == 0
    assert "reconciliation-ok" in executions[0]["steps"][0]["stdout"]

    # Confirm no duplicate execution after waiting
    time.sleep(3)
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
    only one execution appears and it matches the new schedule's timing.
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

    # Wait for execution from the new cron
    executions = _wait_for_execution(e2e_client, script["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "completed"
    assert "replace-ok" in executions[0]["steps"][0]["stdout"]


def test_persistent_schedule_recovers_after_api_restart(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    docker_service_controller: DockerServiceController,
) -> None:
    """An empty runtime projection is restored from the persistent schedule."""
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
    cron, _ = _next_minute_cron()
    schedule = e2e_resources.create_schedule(script["id"], [node["id"]], cron=cron)
    assert schedule["cron"] == cron

    docker_service_controller.restart("api")
    _wait_for_api(e2e_client)

    restored = e2e_client.get(_schedule_url(script["id"]))
    assert restored.status_code == 200, restored.text
    restored_schedule = restored.json()
    assert restored_schedule["enabled"] is True
    assert restored_schedule["cron"] == cron
    assert restored_schedule["next_run_at"] is not None

    executions = _wait_for_execution(e2e_client, script["id"])
    assert len(executions) == 1
    assert executions[0]["status"] == "completed"
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
        cron, run_at = _next_minute_cron()
        e2e_resources.create_schedule(script["id"], [node["id"]], cron=cron)

        await asyncio.sleep(2)
        assert "scheduler.owner.rejected" in docker_service_controller.logs(
            "api-replica"
        )

        docker_service_controller.stop("api")
        api_stopped = True

        ownership_deadline = time.monotonic() + 30
        while time.monotonic() < ownership_deadline:
            if "scheduler.owner.acquired" in docker_service_controller.logs(
                "api-replica"
            ):
                break
            await asyncio.sleep(1)
        else:
            pytest.fail("Scheduler contender did not acquire ownership")

        execution_deadline = run_at.timestamp() + 45
        execution_count = 0
        while time.time() < execution_deadline:
            execution_count = await postgres_connection.fetchval(
                "SELECT count(*) FROM script_executions WHERE script_id = $1",
                UUID(script["id"]),
            )
            if execution_count:
                break
            await asyncio.sleep(1)
        assert execution_count == 1

        await asyncio.sleep(3)
        assert (
            await postgres_connection.fetchval(
                "SELECT count(*) FROM script_executions WHERE script_id = $1",
                UUID(script["id"]),
            )
            == 1
        )

        docker_service_controller.start("api")
        api_stopped = False
        _wait_for_api(e2e_client)
        await asyncio.sleep(2)
        assert "scheduler.owner.rejected" in docker_service_controller.logs("api")
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
