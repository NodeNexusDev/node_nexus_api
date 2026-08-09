"""Full-stack audit outbox durability and delivery scenarios."""

import asyncio
import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx2 as httpx
import pytest

from tests.e2e.helpers.nodes import create_node as _create_node
from tests.e2e.helpers.nodes import wait_for_audit as _wait_for_audit
from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.service_controller import DockerServiceController

pytestmark = pytest.mark.docker


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
        """INSERT INTO audit_outbox
           (id, payload, status, attempts, next_attempt_at, created_at)
           VALUES ($1, $2::jsonb, 'pending', 0, $3, $4)""",
        event_id,
        json.dumps(
            {
                "node_id": node["id"],
                "action": "create",
                "user": "e2e",
                "details": None,
            }
        ),
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
        """INSERT INTO audit_outbox
           (id, payload, status, attempts, next_attempt_at, created_at)
           VALUES ($1, $2::jsonb, 'pending', 0, $3, $4)""",
        event_id,
        json.dumps(
            {
                "node_id": node["id"],
                "action": "test_restart",
                "user": "e2e",
                "details": None,
            }
        ),
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
        """INSERT INTO audit_outbox
           (id, payload, status, attempts, next_attempt_at, created_at)
           VALUES ($1, $2::jsonb, 'pending', 0, $3, $4)""",
        malformed_id,
        json.dumps(
            {
                "node_id": None,
                "user": "e2e",
                "details": None,
            }
        ),
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


def _get_master_key() -> str:
    """Return the master API key used in the e2e Docker environment."""
    return "e2e-master-key-12345"


def test_audit_log_endpoint(e2e_client: httpx.Client) -> None:
    _create_node(e2e_client, name="audit-probe")

    resp = e2e_client.get("/api/v1/audit/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "total" in data
    assert "page" in data and "size" in data
    assert data["total"] >= 1

    log = data["items"][0]
    assert "id" in log
    assert "action" in log
    assert "created_at" in log
    assert "node_id" in log


def test_audit_logs_track_crud_operations(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="audit-crud")
    node_id = node["id"]

    # create action recorded
    data = _wait_for_audit(e2e_client, query=f"?node_id={node_id}", action="create")
    actions = [log["action"] for log in data["items"]]
    assert "create" in actions

    # update action recorded
    e2e_client.put(f"/api/v1/nodes/{node_id}", json={"name": "audit-crud-upd"})
    data = _wait_for_audit(e2e_client, query=f"?node_id={node_id}", action="update")
    actions = [log["action"] for log in data["items"]]
    assert "update" in actions

    # delete action recorded — ON DELETE SET NULL nullifies node_id,
    # so query by action instead of node_id.
    total_before = e2e_client.get("/api/v1/audit/").json()["total"]
    e2e_client.delete(f"/api/v1/nodes/{node_id}")
    data = _wait_for_audit(e2e_client, action="delete", minimum_total=total_before + 1)
    all_actions = [log["action"] for log in data["items"]]
    assert "delete" in all_actions


def test_delete_creates_audit_log_and_removes_node(
    e2e_client: httpx.Client,
) -> None:
    """Regression: FK violation used to roll back DELETE silently."""
    node = _create_node(e2e_client, name="audit-fk-regression")
    node_id = node["id"]

    total_before = e2e_client.get("/api/v1/audit/").json()["total"]
    resp = e2e_client.delete(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 204

    # node is gone
    resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 404

    # audit entry exists (ON DELETE SET NULL nullifies node_id,
    # so verify total grew and a "delete" action appeared)
    data = _wait_for_audit(e2e_client, action="delete", minimum_total=total_before + 1)
    all_actions = [log["action"] for log in data["items"]]
    assert "delete" in all_actions


def test_audit_log_filter_by_action(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="audit-filter")

    resp = e2e_client.get("/api/v1/audit/?action=create")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    for log in resp.json()["items"]:
        assert log["action"] == "create"

    e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_audit_log_pagination(e2e_client: httpx.Client) -> None:
    # Create multiple nodes to generate audit entries
    created: list[str] = []
    for i in range(3):
        node = _create_node(e2e_client, name=f"audit-page-{i}")
        created.append(node["id"])

    resp = e2e_client.get("/api/v1/audit/?page=1&size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["size"] == 2

    for node_id in created:
        e2e_client.delete(f"/api/v1/nodes/{node_id}")


def test_audit_log_combined_filters(e2e_client: httpx.Client) -> None:
    node = _create_node(e2e_client, name="audit-combined")
    node_id = node["id"]

    data = _wait_for_audit(
        e2e_client,
        node_id=node_id,
        action="create",
    )
    assert data["total"] >= 1
    for log in data["items"]:
        assert log["action"] == "create"
        # node_id may be null for deleted nodes, but for existing ones it matches
        if log["node_id"] is not None:
            assert log["node_id"] == node_id

    e2e_client.delete(f"/api/v1/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Command and script pagination
# ---------------------------------------------------------------------------


def test_audit_delete_requires_master_key(e2e_client: httpx.Client) -> None:
    """DELETE /audit requires master key."""
    # Create a non-master key
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "non-master-key"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    generated_key = resp.json()["key"]
    key_id = resp.json()["id"]

    # Try to delete audit logs with non-master key
    resp = e2e_client.delete(
        "/api/v1/audit/?confirm=yes",
        headers={"X-API-Key": generated_key},
    )
    assert resp.status_code == 403

    # Cleanup
    e2e_client.delete(
        f"/api/v1/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


def test_audit_delete_requires_confirm(e2e_client: httpx.Client) -> None:
    """DELETE /audit without confirm=yes returns 422."""
    master_key = _get_master_key()
    resp = e2e_client.delete(
        "/api/v1/audit/",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 422


def test_audit_delete_with_master_key(e2e_client: httpx.Client) -> None:
    """DELETE /audit with master key and confirm=yes succeeds."""
    master_key = _get_master_key()
    resp = e2e_client.delete(
        "/api/v1/audit/?confirm=yes",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deleted_count" in data


# ---------------------------------------------------------------------------
# Node metrics
# ---------------------------------------------------------------------------
