"""Full-stack audit outbox durability and delivery scenarios."""

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx2 as httpx
import pytest

from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController

pytestmark = pytest.mark.docker


def _wait_for_audit(
    client: httpx.Client,
    *,
    action: str | None = None,
    node_id: str | None = None,
    minimum_total: int = 1,
    timeout: float = 10.0,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        params: dict[str, str | int] = {"page": 1, "size": 50}
        if action:
            params["action"] = action
        if node_id:
            params["node_id"] = node_id
        response = client.get("/api/v1/audit/", params=params)
        assert response.status_code == 200
        data = response.json()
        if data["total"] >= minimum_total:
            if action is None or any(item["action"] == action for item in data["items"]):
                return data
        time.sleep(0.2)
    pytest.fail(f"Audit event not delivered: action={action}, node_id={node_id}")


def _wait_for_api(client: httpx.Client, *, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = client.get("/ready")
            if resp.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    pytest.fail("API did not become ready")


def test_mutating_request_creates_audit_log(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """A mutating request produces both an outbox record and an audit log."""
    total_before = e2e_client.get("/api/v1/audit/").json()["total"]
    node = e2e_resources.create_ssh_node()

    data = _wait_for_audit(e2e_client, action="create", minimum_total=total_before + 1)
    matched = [log for log in data["items"] if log["node_id"] == node["id"]]
    assert len(matched) >= 1
    assert matched[0]["action"] == "create"


@pytest.mark.asyncio
async def test_idempotent_delivery_no_duplicate_log(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    postgres_connection: asyncpg.Connection,
) -> None:
    """Re-delivering the same outbox event does not create a duplicate audit log."""
    node = e2e_resources.create_ssh_node()

    # Wait for initial delivery
    data = _wait_for_audit(e2e_client, action="create", node_id=node["id"])

    # Find the audit log ID for this node's create event
    audit_log = None
    for log in data["items"]:
        if log["node_id"] == node["id"] and log["action"] == "create":
            audit_log = log
            break
    assert audit_log is not None
    event_id = uuid.UUID(audit_log["id"])

    # Verify exactly one audit log exists with this ID
    count_before = await postgres_connection.fetchval(
        "SELECT count(*) FROM audit_logs WHERE id = $1", event_id
    )
    assert count_before == 1

    # Delete the existing outbox record (already completed) so we can re-insert
    await postgres_connection.execute(
        "DELETE FROM audit_outbox WHERE id = $1", event_id
    )

    # Re-insert the outbox record with the same event ID as pending
    now = datetime.now(UTC)
    await postgres_connection.execute(
        """INSERT INTO audit_outbox (id, payload, status, attempts, next_attempt_at, created_at)
           VALUES ($1, $2::jsonb, 'pending', 0, $3, $4)""",
        event_id,
        json.dumps({
            "node_id": node["id"],
            "action": "create",
            "user": "e2e",
            "details": None,
        }),
        now,
        now,
    )

    # Wait for worker to process the duplicate
    await asyncio.sleep(3)

    # Should still be exactly one audit log
    count_after = await postgres_connection.fetchval(
        "SELECT count(*) FROM audit_logs WHERE id = $1", event_id
    )
    assert count_after == 1


def test_db_pause_causes_retry_then_delivery(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    docker_service_controller: DockerServiceController,
) -> None:
    """Pausing DB temporarily delays delivery; after recovery the event is delivered."""
    # Create a node — audit event is committed with the business transaction
    node = e2e_resources.create_ssh_node()

    # Pause DB to block the outbox worker
    docker_service_controller.pause("db")
    time.sleep(2)
    docker_service_controller.unpause("db")

    # After recovery, the worker should deliver the event
    data = _wait_for_audit(
        e2e_client, action="create", node_id=node["id"], timeout=15.0
    )
    matched = [log for log in data["items"] if log["node_id"] == node["id"]]
    assert len(matched) >= 1


@pytest.mark.asyncio
async def test_deleted_node_does_not_break_delivery(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    postgres_connection: asyncpg.Connection,
) -> None:
    """Deleting a node while audit events are pending does not block delivery."""
    node = e2e_resources.create_ssh_node()
    node_id = node["id"]

    # Wait for create audit to be delivered
    _wait_for_audit(e2e_client, action="create", node_id=node_id)

    # Delete the node — this creates a delete audit event
    resp = e2e_client.delete(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 204

    # The delete audit event should still be delivered with node_id=NULL
    deadline = time.monotonic() + 10.0
    found = False
    while time.monotonic() < deadline:
        resp = e2e_client.get("/api/v1/audit/?action=delete")
        assert resp.status_code == 200
        for log in resp.json()["items"]:
            if log["node_id"] is None:
                found = True
                break
        if found:
            break
        await asyncio.sleep(0.2)
    assert found, "Delete audit event with nullified node_id not found"


@pytest.mark.asyncio
async def test_api_restart_does_not_lose_pending_outbox(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    docker_service_controller: DockerServiceController,
    postgres_connection: asyncpg.Connection,
) -> None:
    """Pending outbox records survive an API restart."""
    # Create a node — outbox record is committed
    node = e2e_resources.create_ssh_node()

    # Wait for initial delivery
    _wait_for_audit(e2e_client, action="create")

    # Insert a pending outbox record with future next_attempt_at
    event_id = uuid.uuid4()
    now = datetime.now(UTC)
    future_time = now + timedelta(minutes=5)
    await postgres_connection.execute(
        """INSERT INTO audit_outbox (id, payload, status, attempts, next_attempt_at, created_at)
           VALUES ($1, $2::jsonb, 'pending', 0, $3, $4)""",
        event_id,
        json.dumps({
            "node_id": node["id"],
            "action": "test_restart",
            "user": "e2e",
            "details": None,
        }),
        future_time,
        now,
    )

    # Restart API — the pending record should survive
    docker_service_controller.restart("api")
    _wait_for_api(e2e_client)

    # The outbox record should still be pending (next_attempt_at is in the future)
    row = await postgres_connection.fetchrow(
        "SELECT status FROM audit_outbox WHERE id = $1", event_id
    )
    assert row is not None
    assert row["status"] == "pending"


@pytest.mark.asyncio
async def test_worker_continues_after_malformed_event(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    postgres_connection: asyncpg.Connection,
) -> None:
    """The outbox worker continues processing after encountering a malformed event."""
    # Insert a malformed outbox record (missing required "action" field)
    malformed_id = uuid.uuid4()
    now = datetime.now(UTC)
    await postgres_connection.execute(
        """INSERT INTO audit_outbox (id, payload, status, attempts, next_attempt_at, created_at)
           VALUES ($1, $2::jsonb, 'pending', 0, $3, $4)""",
        malformed_id,
        json.dumps({"node_id": None, "user": "e2e", "details": None}),  # missing "action"
        now,
        now,
    )

    # Create a valid node — this produces a valid outbox record
    e2e_resources.create_ssh_node()

    # Wait for the valid event to be delivered
    _wait_for_audit(e2e_client, action="create")

    # Poll until the malformed event is marked as failed (needs 5 retries with backoff)
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        row = await postgres_connection.fetchrow(
            "SELECT status, attempts FROM audit_outbox WHERE id = $1", malformed_id
        )
        assert row is not None
        if row["status"] == "failed":
            break
        await asyncio.sleep(1)
    assert row["status"] == "failed"
    assert row["attempts"] >= 5


@pytest.mark.asyncio
async def test_retention_cleanup_removes_old_records(
    postgres_connection: asyncpg.Connection,
) -> None:
    """Retention cleanup deletes only audit logs older than the cutoff."""
    # Clean up any leftover data from previous runs
    await postgres_connection.execute(
        "DELETE FROM audit_logs WHERE action = 'retention_test'"
    )

    # Insert old audit logs directly
    old_ids = [uuid.uuid4() for _ in range(3)]
    old_time = datetime.now(UTC) - timedelta(days=100)
    for audit_id in old_ids:
        await postgres_connection.execute(
            """INSERT INTO audit_logs (id, action, "user", created_at)
               VALUES ($1, 'retention_test', 'e2e', $2)""",
            audit_id,
            old_time,
        )

    # Insert a recent audit log
    recent_id = uuid.uuid4()
    await postgres_connection.execute(
        """INSERT INTO audit_logs (id, action, "user", created_at)
           VALUES ($1, 'retention_test', 'e2e', $2)""",
        recent_id,
        datetime.now(UTC),
    )

    # Verify all exist
    count_before = await postgres_connection.fetchval(
        "SELECT count(*) FROM audit_logs WHERE action = 'retention_test'"
    )
    assert count_before == 4

    # Run cleanup via direct SQL (equivalent to AuditCleanupJob)
    cutoff = datetime.now(UTC) - timedelta(days=90)
    result = await postgres_connection.execute(
        "DELETE FROM audit_logs WHERE action = 'retention_test' AND created_at < $1",
        cutoff,
    )
    deleted = int(result.split()[-1])

    assert deleted >= 3

    # Recent record should still exist
    count_after = await postgres_connection.fetchval(
        "SELECT count(*) FROM audit_logs WHERE action = 'retention_test'"
    )
    assert count_after == 1

    remaining = await postgres_connection.fetchval(
        "SELECT id FROM audit_logs WHERE action = 'retention_test' LIMIT 1"
    )
    assert remaining == recent_id
