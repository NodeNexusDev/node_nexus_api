"""E2E tests for script CRUD, execute, schedule, scheduler execution."""

import asyncio
from uuid import uuid4

import httpx2 as httpx
import pytest
from pytest_docker.plugin import Services
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.runtime.apscheduler_runtime import ApschedulerRuntime
from tests.e2e.helpers.polling import wait_for_condition
from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.types import UnvalidatedJsonObject

pytestmark = pytest.mark.docker


_SCHEDULE_LOCK_ID = 5_642_395_847_322_111


async def _wait_for_api_owns_lock(engine, *, timeout: float = 30.0) -> None:
    """Block until the running API owns the scheduler advisory lock.

    The flaky race: a prior failover test may have released the lock and the
    API is still restarting. If a contender runs before the API reacquires the
    lock, ``pg_try_advisory_lock`` returns True and the assertion fails. We
    poll by attempting to grab the lock ourselves; if we succeed, the API does
    NOT own it, so we release and wait, retrying until the API holds the lock.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        probe = ApschedulerRuntime()
        try:
            acquired = await probe.acquire_ownership(engine)
        finally:
            await probe.stop()
        if not acquired:
            return
        # API does not currently own the lock — wait and retry.
        await asyncio.sleep(0.5)
    raise AssertionError(
        "API did not re-acquire the scheduler advisory lock within "
        f"{timeout}s — readiness probe failed"
    )


def _unwrap_id(resp: httpx.Response, *, id_field: str = "id") -> str:
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        first = data["results"][0]
        return str(first.get(id_field) or first.get("id") or first.get("node_id"))
    return str(data["id"])


def _unwrap_item(  # noqa: E501
    resp: httpx.Response, payload: dict[str, object], *, id_field: str = "id"
) -> UnvalidatedJsonObject:
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        first = data["results"][0]
        raw = first.get(id_field) or first.get("id") or first.get("node_id")
        assert raw is not None, f"Missing id in bulk result {first}"
        nid = str(raw)
        compat: UnvalidatedJsonObject = dict(payload)
        compat["id"] = nid
        for k, v in first.items():
            if k not in compat:
                compat[k] = v
        compat["id"] = nid
        return compat
    return data  # type: ignore[return-value]


def _create_command(
    e2e_client: httpx.Client, **overrides: object
) -> UnvalidatedJsonObject:
    """Helper to create a command template (bulk-first)."""
    data = {
        "name": "e2e-command",
        "command": "echo test",
        "description": "E2E test command",
        **overrides,
    }
    resp = e2e_client.post("/api/v2/commands/", json={"items": [data]})
    assert resp.status_code in (200, 201, 207)
    body = resp.json()
    if isinstance(body, dict) and "results" in body:
        first = body["results"][0]
        assert first.get("status") == "success", f"create failed {first}"
        compat = dict(data)
        compat["id"] = str(first.get("id"))
        # Fetch full object
        cid = compat["id"]
        get_resp = e2e_client.get(f"/api/v2/commands/{cid}")
        if get_resp.status_code == 200:
            return get_resp.json()
        return compat  # type: ignore[return-value]
    return body  # type: ignore[return-value]


def _create_script(
    e2e_client: httpx.Client, **overrides: object
) -> UnvalidatedJsonObject:
    """Helper to create a script (bulk-first)."""
    steps = [
        {
            "label": "Check disk",
            "type": "inline",
            "command": "df -h",
            "on_failure": "stop",
        }
    ]
    data = {
        "name": "e2e-script",
        "description": "E2E test script",
        "steps": steps,
        **overrides,
    }
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [data]})
    assert resp.status_code in (200, 201, 207)
    body = resp.json()
    if isinstance(body, dict) and "results" in body:
        first = body["results"][0]
        assert first.get("status") == "success", f"create failed {first}"
        compat = dict(data)
        compat["id"] = str(first.get("id"))
        sid = compat["id"]
        get_resp = e2e_client.get(f"/api/v2/scripts/{sid}")
        if get_resp.status_code == 200:
            return get_resp.json()
        return compat  # type: ignore[return-value]
    return body  # type: ignore[return-value]


def test_script_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    script = _create_script(e2e_client, name="script-create")
    script_id = script["id"]
    assert script["name"] == "script-create"
    assert len(script["steps"]) == 1

    # Read
    resp = e2e_client.get(f"/api/v2/scripts/{script_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "script-create"

    # Read all — CursorPage
    resp = e2e_client.get("/api/v2/scripts/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "has_more" in data
    assert "next_cursor" in data
    assert "limit" in data
    assert len(data["items"]) >= 1

    # Update
    resp = e2e_client.patch(
        f"/api/v2/scripts/{script_id}",
        json={"name": "script-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "script-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v2/scripts/{script_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v2/scripts/{script_id}")
    assert resp.status_code == 404


def test_script_create_multiple_steps(e2e_client: httpx.Client) -> None:
    _payload = {
        "name": "multi-step",
        "steps": [
            {"label": "Step 1", "type": "inline", "command": "echo 1"},
            {
                "label": "Step 2",
                "type": "inline",
                "command": "echo 2",
                "on_failure": "continue",
            },
        ],
    }
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [_payload]})
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    get_resp = e2e_client.get(f"/api/v2/scripts/{script_id}")
    assert get_resp.status_code == 200
    script = get_resp.json()
    assert len(script["steps"]) == 2
    assert script["steps"][0]["label"] == "Step 1"
    assert script["steps"][1]["on_failure"] == "continue"
    e2e_client.delete(f"/api/v2/scripts/{script_id}")


def test_script_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [{"name": "no-steps"}]})
    assert resp.status_code == 422


def test_script_not_found(e2e_client: httpx.Client) -> None:
    fake_id = str(uuid4())
    resp = e2e_client.get(f"/api/v2/scripts/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.patch(f"/api/v2/scripts/{fake_id}", json={"name": "x"})
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v2/scripts/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Script execution (requires SSH node)
# ---------------------------------------------------------------------------


def test_script_execute_on_ssh_node(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="script-exec")
    script = _create_script(e2e_client, name="exec-script")

    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [script["id"]], "node_ids": [node["id"]]},
    )
    assert resp.status_code in (200, 207)
    batch = resp.json()
    assert batch["total"] == 1
    assert batch["succeeded"] == 1
    assert len(batch["results"]) == 1
    result = batch["results"][0]
    assert str(result["node_id"]) == node["id"]
    assert str(result["script_id"]) == script["id"]
    assert result["status"] == "success"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["exit_code"] == 0


def test_script_execute_not_found(e2e_client: httpx.Client) -> None:
    fake_script = str(uuid4())
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [fake_script], "node_ids": [str(uuid4())]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_script_execute_node_not_found(e2e_client: httpx.Client) -> None:
    script = _create_script(e2e_client, name="no-node-script")
    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [script["id"]], "node_ids": [str(uuid4())]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "error"


def test_script_executions_history(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="script-hist")
    script = _create_script(e2e_client, name="hist-script")

    # Execute via bulk endpoint
    e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [script["id"]], "node_ids": [node["id"]]},
    )

    # Check history — CursorPage
    resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/executions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 1
    assert "has_more" in data
    assert "next_cursor" in data
    assert "limit" in data
    execution = data["items"][0]
    assert execution["status"] == "success"
    assert execution["node_id"] == node["id"]


def test_script_executions_not_found(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get(f"/api/v2/scripts/{uuid4()}/executions")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Connection type validation
# ---------------------------------------------------------------------------


def test_script_pagination(e2e_client: httpx.Client) -> None:
    created: list[str] = []
    for i in range(3):
        script = _create_script(e2e_client, name=f"page-script-{i}")
        created.append(script["id"])

    resp = e2e_client.get("/api/v2/scripts/?cursor=&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert "has_more" in data
    assert "next_cursor" in data
    assert data["has_more"] is True
    assert data["limit"] == 2

    for script_id in created:
        e2e_client.delete(f"/api/v2/scripts/{script_id}")


# ---------------------------------------------------------------------------
# Script execute with command reference steps
# ---------------------------------------------------------------------------


def test_script_execute_with_command_reference(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node = e2e_resources.create_ssh_node(name="script-cmd-ref")
    cmd = _create_command(e2e_client, name="ref-cmd", command="echo ref-ok")

    _payload = {
        "name": "cmd-ref-script",
        "steps": [
            {
                "label": "Run referenced cmd",
                "type": "command",
                "command_id": cmd["id"],
                "on_failure": "stop",
            }
        ],
    }
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [_payload]})
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    get_resp = e2e_client.get(f"/api/v2/scripts/{script_id}")
    if get_resp.status_code == 200:
        script = get_resp.json()
    else:
        script = {"id": script_id, **_payload}  # type: ignore[dict-item]

    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={"script_ids": [script["id"]], "node_ids": [node["id"]]},
    )
    assert resp.status_code in (200, 207)
    batch = resp.json()
    assert batch["succeeded"] == 1
    assert len(batch["results"]) == 1
    result = batch["results"][0]
    assert result["status"] == "success"
    assert result["steps"][0]["stdout"].strip() == "ref-ok"


def test_script_execute_multi_node(
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    node1 = e2e_resources.create_ssh_node(name="multi-node-1")
    node2 = e2e_resources.create_ssh_node(name="multi-node-2")
    script = _create_script(e2e_client, name="multi-script")

    resp = e2e_client.post(
        "/api/v2/scripts/executions",
        json={
            "script_ids": [script["id"]],
            "node_ids": [node1["id"], node2["id"]],
        },
    )
    assert resp.status_code in (200, 207)
    batch = resp.json()
    assert batch["total"] == 2
    assert batch["succeeded"] == 2
    assert len(batch["results"]) == 2
    node_ids = {str(r["node_id"]) for r in batch["results"]}
    assert node1["id"] in node_ids
    assert node2["id"] in node_ids
    for r in batch["results"]:
        assert r["status"] == "success"


# ---------------------------------------------------------------------------
# Command partial update and edge cases
# ---------------------------------------------------------------------------


def test_script_partial_update(e2e_client: httpx.Client) -> None:
    script = _create_script(e2e_client, name="script-partial")

    resp = e2e_client.patch(
        f"/api/v2/scripts/{script['id']}",
        json={"name": "script-partial-updated"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "script-partial-updated"
    assert len(updated["steps"]) == 1  # steps unchanged


# ---------------------------------------------------------------------------
# Node port validation
# ---------------------------------------------------------------------------


def test_script_with_tags(e2e_client: httpx.Client) -> None:
    """Scripts can be created with tags and filtered by tag."""
    # Create script with tags
    _payload = {
        "name": "tagged-script",
        "steps": [{"label": "Step 1", "type": "inline", "command": "echo ok"}],
        "tags": ["deploy", "staging"],
    }
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [_payload]})
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    get_resp = e2e_client.get(f"/api/v2/scripts/{script_id}")
    assert get_resp.status_code == 200
    script = get_resp.json()
    assert sorted(script["tags"]) == ["deploy", "staging"]

    # Filter by tag
    resp = e2e_client.get("/api/v2/scripts/?tag=deploy")
    assert resp.status_code == 200
    data = resp.json()
    names = {s["name"] for s in data["items"]}
    assert "tagged-script" in names

    # Cleanup
    e2e_client.delete(f"/api/v2/scripts/{script_id}")


# ---------------------------------------------------------------------------
# Audit log cleanup
# ---------------------------------------------------------------------------


_INLINE_STEP = [{"label": "step1", "type": "inline", "command": "echo ok"}]


def test_script_schedule(e2e_client: httpx.Client) -> None:
    """POST /scripts/{id}/schedule schedules a script."""
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"items": [{"name": "sched-e2e-script", "steps": _INLINE_STEP}]},
    )
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "sched-e2e-node",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    try:
        resp = e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "0 9 * * *", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["cron"] == "0 9 * * *"
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


def test_script_unschedule(e2e_client: httpx.Client) -> None:
    """DELETE /scripts/{id}/schedule removes schedule."""
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"items": [{"name": "unsched-e2e-script", "steps": _INLINE_STEP}]},
    )
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "unsched-e2e-node",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    try:
        e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "0 9 * * *", "node_ids": [node["id"]]},
        )
        resp = e2e_client.delete(f"/api/v2/scripts/{script['id']}/schedules")
        assert resp.status_code == 204
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


def test_script_get_schedule(e2e_client: httpx.Client) -> None:
    """GET /scripts/{id}/schedule returns schedule info."""
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"items": [{"name": "getsched-e2e", "steps": _INLINE_STEP}]},
    )
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "getsched-e2e-node",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    try:
        e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "0 9 * * *", "node_ids": [node["id"]]},
        )
        resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/schedules")
        assert resp.status_code == 200
        assert "cron" in resp.json()
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


def test_script_get_schedule_not_found(e2e_client: httpx.Client) -> None:
    """GET /scripts/{id}/schedule returns 404 when not scheduled."""
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"items": [{"name": "nosched-e2e", "steps": _INLINE_STEP}]},
    )
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    try:
        resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/schedules")
        assert resp.status_code == 404
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")


def test_script_schedule_nonexistent(e2e_client: httpx.Client) -> None:
    """POST /scripts/{id}/schedule returns 404 for missing script."""
    resp = e2e_client.post(
        f"/api/v2/scripts/{uuid4()}/schedules",
        json={"cron": "0 9 * * *", "node_ids": [str(uuid4())]},
    )
    assert resp.status_code == 404


def test_script_schedule_invalid_cron(e2e_client: httpx.Client) -> None:
    """POST /scripts/{id}/schedule returns 422 for invalid cron expression."""
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"items": [{"name": "invalid-cron-script", "steps": _INLINE_STEP}]},
    )
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "invalid-cron-node",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    try:
        resp = e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "not-a-valid-cron", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 422
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


@pytest.mark.e2e_scheduler
async def test_second_scheduler_replica_cannot_acquire_ownership(
    docker_ip: str,
    docker_services: Services,
) -> None:
    """The running API owns the advisory lock, so a contender is rejected."""
    database_port = docker_services.port_for("db", 5432)
    engine = create_async_engine(
        f"postgresql+asyncpg://postgres:postgres@{docker_ip}:{database_port}"
        "/node_nexus_e2e"
    )
    try:
        # Ensure the primary API holds the advisory lock before testing the
        # contender, to avoid a flaky race after an earlier failover test.
        await _wait_for_api_owns_lock(engine, timeout=30)
        contender = ApschedulerRuntime()
        try:
            assert await contender.acquire_ownership(engine) is False
            assert contender.owns_execution is False
        finally:
            await contender.stop()
    finally:
        await engine.dispose()


def test_script_schedule_rejects_invalid_trigger_options(
    e2e_client: httpx.Client,
) -> None:
    """Invalid cron, timezone, and misfire grace are rejected without side effects."""
    resp = e2e_client.post(
        "/api/v2/scripts/",
        json={"items": [{"name": "badcron-e2e", "steps": _INLINE_STEP}]},
    )
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "badcron-e2e-node",
                    "host": "10.0.0.1",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    try:
        invalid_payloads = (
            {"cron": "invalid", "node_ids": [node["id"]]},
            {
                "cron": "* * * * *",
                "node_ids": [node["id"]],
                "timezone": "Mars/Olympus_Mons",
            },
            {
                "cron": "* * * * *",
                "node_ids": [node["id"]],
                "misfire_grace_seconds": 0,
            },
        )
        for payload in invalid_payloads:
            resp = e2e_client.post(
                f"/api/v2/scripts/{script['id']}/schedules",
                json=payload,
            )
            assert resp.status_code == 422, resp.text

        current = e2e_client.get(f"/api/v2/scripts/{script['id']}/schedules")
        assert current.status_code == 404
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Scheduler execution — Stage D.1
# ---------------------------------------------------------------------------


@pytest.mark.e2e_scheduler
def test_scheduler_executes_script_on_cron(e2e_client: httpx.Client) -> None:
    """Scheduled script actually executes and produces history.

    Creates an SSH node, a simple script, schedules it, then triggers the
    schedule immediately through the E2E harness endpoint and verifies the
    execution record.
    """

    # Create node
    node_data = {
        "name": "sched-exec-node",
        "host": "ssh-server",
        "port": 2222,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [node_data]})
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    # Create script
    _script_payload = {
        "name": "sched-exec-script",
        "steps": [{"label": "s1", "type": "inline", "command": "echo scheduled-ok"}],
    }
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [_script_payload]})
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    try:
        # Register, then replace the same runtime job with a per-minute cron.
        resp = e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "*/2 * * * *", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 200
        assert resp.json()["cron"] == "*/2 * * * *"
        resp = e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "* * * * *", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 200
        schedule = resp.json()
        assert schedule["cron"] == "* * * * *"

        # Trigger execution immediately instead of waiting for the next minute.
        resp = e2e_client.post(
            f"/api/v2/internal/e2e/scheduler/{script['id']}/trigger-now"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"

        def _execution_completed() -> bool:
            resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/executions")
            if resp.status_code != 200:
                return False
            data = resp.json()
            if len(data.get("items", [])) == 0:
                return False
            exec_item = data["items"][0]
            return bool(exec_item["status"] == "success")

        wait_for_condition(
            _execution_completed,
            timeout=10.0,
            pause=0.2,
            description="scheduled execution to complete",
        )

        history = e2e_client.get(f"/api/v2/scripts/{script['id']}/executions")
        assert history.status_code == 200
        data = history.json()
        assert len(data["items"]) == 1
        exec_item = data["items"][0]
        assert exec_item["started_at"] is not None
        assert exec_item["finished_at"] is not None
        assert len(exec_item["steps"]) == 1
        assert "scheduled-ok" in exec_item["steps"][0]["stdout"]
        assert exec_item["steps"][0]["exit_code"] == 0

        # Verify schedule metadata updated
        resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/schedules")
        assert resp.status_code == 200
        schedule_after = resp.json()
        assert schedule_after["last_run_at"] is not None
        assert schedule_after["last_success_at"] is not None
        assert schedule_after["next_run_at"] is not None

    finally:
        # Unschedule and cleanup
        e2e_client.delete(f"/api/v2/scripts/{script['id']}/schedules")
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


@pytest.mark.e2e_scheduler
def test_scheduler_records_failed_execution(e2e_client: httpx.Client) -> None:
    """Scheduled script with failing command records failed execution."""

    node_data = {
        "name": "sched-fail-node",
        "host": "ssh-server",
        "port": 2222,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }
    resp = e2e_client.post("/api/v2/nodes/", json={"items": [node_data]})
    assert resp.status_code in (200, 201, 207)
    node_id = _unwrap_id(resp, id_field="node_id")
    node = e2e_client.get(f"/api/v2/nodes/{node_id}").json()

    _script_payload = {
        "name": "sched-fail-script",
        "steps": [{"label": "s1", "type": "inline", "command": "exit 1"}],
    }
    resp = e2e_client.post("/api/v2/scripts/", json={"items": [_script_payload]})
    assert resp.status_code in (200, 201, 207)
    script_id = _unwrap_id(resp, id_field="id")
    script = e2e_client.get(f"/api/v2/scripts/{script_id}").json()

    try:
        resp = e2e_client.post(
            f"/api/v2/scripts/{script['id']}/schedules",
            json={"cron": "* * * * *", "node_ids": [node["id"]]},
        )
        assert resp.status_code == 200

        # Trigger execution immediately; the harness endpoint records failures.
        resp = e2e_client.post(
            f"/api/v2/internal/e2e/scheduler/{script['id']}/trigger-now"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

        def _execution_recorded() -> bool:
            resp = e2e_client.get(f"/api/v2/scripts/{script['id']}/executions")
            if resp.status_code != 200:
                return False
            return bool(len(resp.json().get("items", [])) > 0)

        wait_for_condition(
            _execution_recorded,
            timeout=10.0,
            pause=0.2,
            description="failed scheduled execution to be recorded",
        )

        data = e2e_client.get(f"/api/v2/scripts/{script['id']}/executions").json()
        exec_item = data["items"][0]
        # Non-zero exit should be recorded on the step and status.
        step_exit_code = exec_item["steps"][0]["exit_code"]
        status = exec_item.get("status", "")
        assert step_exit_code != 0 or "fail" in status.lower(), (
            f"Expected failed execution, got: {exec_item}"
        )
    finally:
        e2e_client.delete(f"/api/v2/scripts/{script['id']}/schedules")
        e2e_client.delete(f"/api/v2/scripts/{script['id']}")
        e2e_client.delete(f"/api/v2/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker E2E helpers
# ---------------------------------------------------------------------------
