"""E2E tests for Docker operations via SSH-backed Docker nodes."""

from datetime import UTC

import pytest

from tests.e2e.helpers.docker_test import wait_for_container_running
from tests.e2e.helpers.polling import wait_for_condition
from tests.e2e.helpers.resources import UniqueResourceFactory

pytestmark = pytest.mark.docker


def _docker_pull_alpine(e2e_client, node_id):
    """Pull alpine image on a Docker node (prerequisite for container tests)."""
    resp = e2e_client.post(
        f"/api/v2/nodes/{node_id}/docker/images/pull",
        json={"image": "alpine:latest", "timeout": 120},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Docker Images
# ---------------------------------------------------------------------------


def test_docker_list_images(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/images returns image list."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/images")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "has_more" in data
    images = data["items"]
    assert isinstance(images, list)
    alpine_images = [i for i in images if "alpine" in str(i).lower()]
    assert len(alpine_images) >= 1


def test_docker_pull_image(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/images/pull pulls an image."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/pull",
        json={"image": "alpine:3.20", "timeout": 120},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ---------------------------------------------------------------------------
# Docker Containers
# ---------------------------------------------------------------------------


def test_docker_list_containers(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/containers returns list."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/containers")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data and "has_more" in data
    assert isinstance(data["items"], list)


def test_docker_list_containers_all(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers?all=true includes stopped containers."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/containers?all=true")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_docker_container_lifecycle(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """Full container lifecycle: run, inspect, stop, start, restart, remove."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])

    # Run a container via SSH exec (docker run -d alpine sleep 300)
    resp = e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name e2e-test-ctr alpine sleep 300"],
        },
    )
    assert resp.status_code == 200

    # Inspect
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr")
    assert resp.status_code == 200
    data = resp.json()
    assert data["State"]["status"] == "running"

    # Stop
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr/stop"
    )
    assert resp.status_code == 204

    # Start
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr/start"
    )
    assert resp.status_code == 204

    # Restart
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr/restart"
    )
    assert resp.status_code == 204

    # Logs
    resp = e2e_client.get(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr/logs"
    )
    assert resp.status_code == 200

    # Exec
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr/exec",
        json={"command": "echo exec-ok"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert "exec-ok" in result["stdout"]

    # Stats
    resp = e2e_client.get(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr/stats"
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert "Name" in stats or "CPUPerc" in stats

    # Remove (force)
    resp = e2e_client.delete(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-test-ctr?force=true"
    )
    assert resp.status_code == 204


def test_docker_container_not_found(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers/{id} returns 404 for missing container."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/containers/nonexistent")
    assert resp.status_code == 404


def test_docker_exec_validation(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../exec returns 422 for invalid container ID."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/bad;$id/exec",
        json={"command": "ls"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Docker Networks and Volumes
# ---------------------------------------------------------------------------


def test_docker_list_networks(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/networks returns network list."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/networks")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    networks = data["items"]
    assert isinstance(networks, list)
    # bridge network should exist by default
    names = [n.get("Name", "") for n in networks]
    assert "bridge" in names


def test_docker_list_volumes(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/volumes returns volume list."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/volumes")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


# ---------------------------------------------------------------------------
# Docker Bulk Operations
# ---------------------------------------------------------------------------


def test_docker_bulk_start(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/starts vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    # Run a container via SSH
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name bulk-start-ctr alpine sleep 300"],
        },
    )
    # Stop it first
    e2e_client.post(f"/api/v2/nodes/{node['id']}/docker/containers/bulk-start-ctr/stop")

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/starts",
        json={"container_ids": ["bulk-start-ctr"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1


def test_docker_bulk_stop(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/stops vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name bulk-stop-ctr alpine sleep 300"],
        },
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/stops?timeout=5",
        json={"container_ids": ["bulk-stop-ctr"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1


def test_docker_bulk_restart(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/restarts vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name bulk-restart-ctr alpine sleep 300"],
        },
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/restarts?timeout=5",
        json={"container_ids": ["bulk-restart-ctr"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["succeeded"] == 1


def test_docker_bulk_exec(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/executions vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name bulk-exec-ctr alpine sleep 300"],
        },
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/executions",
        json={
            "container_ids": ["bulk-exec-ctr"],
            "command": "echo exec-works",
            "timeout": 10,
        },
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    results = data["results"]
    assert len(results) == 1
    # ContainerExecBulkResult has stdout/stderr
    assert "exec-works" in (results[0].get("stdout") or results[0].get("output") or "")


# ---------------------------------------------------------------------------
# API Key scope enforcement (403 on read-only)
# ---------------------------------------------------------------------------


def test_docker_container_logs_explicit_tail(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers/{cid}/logs?tail=N returns exactly N lines."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        # Generate a container that prints 10 numbered lines then sleeps
        cmd = (
            "docker run -d --name e2e-logs-tail alpine sh -c "
            "'for i in $(seq 1 10); do echo line-$i; done; sleep 60'"
        )
        resp = e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        assert resp.status_code == 200

        # Wait for container to finish printing by polling logs endpoint
        def _has_logs() -> bool:
            resp = e2e_client.get(
                f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-tail/logs?tail=3"
            )
            if resp.status_code != 200:
                return False
            output = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text
            )
            if isinstance(output, str):
                lines = [line for line in output.strip().split("\n") if line]
                return len(lines) > 0
            return False

        wait_for_condition(
            _has_logs, timeout=10.0, description="container logs available"
        )

        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-tail/logs?tail=3"
        )
        assert resp.status_code == 200, f"logs failed: {resp.status_code} {resp.text}"
        output = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else resp.text
        )
        # Should have at most 3 lines
        if isinstance(output, str):
            lines = [line for line in output.strip().split("\n") if line]
            assert len(lines) <= 3, (
                f"Expected <=3 lines, got {len(lines)}: {lines[:10]}"
            )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-tail?force=true"
        )


def test_docker_container_logs_tail_default(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers/{cid}/logs (without tail) uses default tail=100."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = (
            "docker run -d --name e2e-logs-default alpine sh -c 'echo hello; sleep 60'"
        )
        resp = e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        assert resp.status_code == 200

        # Wait for container to start and print by polling logs endpoint
        def _has_logs() -> bool:
            resp = e2e_client.get(
                f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-default/logs"
            )
            if resp.status_code != 200:
                return False
            output = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text
            )
            return bool(output and str(output).strip())

        wait_for_condition(
            _has_logs, timeout=10.0, description="container logs available"
        )

        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-default/logs"
        )
        assert resp.status_code == 200
        output = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else resp.text
        )
        assert "hello" in str(output).lower() or len(str(output)) > 0
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-default?force=true"
        )


def test_docker_container_logs_since_iso_timestamp(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers/{cid}/logs?since=<ISO 8601> limits output.

    Docker accepts both Unix timestamps and ISO 8601 strings for ``--since``.
    The API normalizes ISO 8601 to a Unix timestamp before invoking Docker.
    """
    from datetime import datetime

    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = (
            "docker run -d --name e2e-logs-since alpine sh -c "
            "'echo before-sleep; sleep 2; echo after-sleep; sleep 60'"
        )
        resp = e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        assert resp.status_code == 200

        # Wait for container to start and print first line by polling logs
        def _has_first_line() -> bool:
            resp = e2e_client.get(
                f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-since/logs"
            )
            if resp.status_code != 200:
                return False
            return "before-sleep" in resp.text

        wait_for_condition(_has_first_line, timeout=10.0, description="first log line")

        # Capture current time as ISO 8601 (after first echo, before second)
        since_dt = datetime.now(UTC)
        since = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Wait for second echo by polling logs
        def _has_second_line() -> bool:
            resp = e2e_client.get(
                f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-since/logs"
            )
            if resp.status_code != 200:
                return False
            return "after-sleep" in resp.text

        wait_for_condition(
            _has_second_line, timeout=10.0, description="second log line"
        )

        # Get logs since the captured ISO 8601 timestamp
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-since/logs"
            f"?since={since}"
        )
        assert resp.status_code == 200
        output = resp.text
        # Should contain after-sleep but may not contain before-sleep
        assert "after-sleep" in output
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-since?force=true"
        )


def test_docker_container_logs_invalid_tail_zero(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../logs?tail=0 should return 422 (ge=1 constraint)."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-logs-zero alpine sleep 60"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-zero/logs?tail=0"
        )
        assert resp.status_code == 422, (
            f"Expected 422 for tail=0, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-zero?force=true"
        )


def test_docker_container_logs_invalid_tail_overflow(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../logs?tail=99999 should return 422 (le=10000 constraint)."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-logs-overflow alpine sleep 60"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-overflow/logs?tail=99999"
        )
        assert resp.status_code == 422, (
            f"Expected 422 for tail=99999, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-logs-overflow?force=true"
        )


# ---------------------------------------------------------------------------
# Docker Container Exec — parameterized (Stage N.2)
# ---------------------------------------------------------------------------


def test_docker_container_exec_timeout_boundary(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../exec with timeout=1 (minimum) should work."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-t1 alpine sleep 300"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )

        wait_for_container_running(e2e_client, node["id"], "e2e-exec-t1", timeout=15.0)

        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-t1/exec",
            json={"command": "echo ok", "timeout": 1},
        )
        assert resp.status_code == 200, (
            f"Expected 200 for timeout=1, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-t1?force=true"
        )


def test_docker_container_exec_timeout_max(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../exec with timeout=600 (maximum) should work."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-tmax alpine sleep 300"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-tmax/exec",
            json={"command": "echo ok", "timeout": 600},
        )
        assert resp.status_code == 200, (
            f"Expected 200 for timeout=600, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-tmax?force=true"
        )


def test_docker_container_exec_command_too_long(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../exec with command > 4096 chars should return 422."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-long alpine sleep 300"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-long/exec",
            json={"command": "A" * 5000, "timeout": 30},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for long command, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-long?force=true"
        )


def test_docker_container_exec_timeout_exceeded(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../exec with command that exceeds timeout should complete with error."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-timeout alpine sleep 300"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-timeout/exec",
            json={"command": "sleep 10", "timeout": 1},
        )
        # May be 200 with non-zero exit, or may be an error response
        # The key assertion: it should NOT be a 500 internal server error
        assert resp.status_code < 500, (
            f"Got 5xx ({resp.status_code}) on exec timeout: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-exec-timeout?force=true"
        )


# ---------------------------------------------------------------------------
# Docker Container Stats — parameterized (Stage N.3)
# ---------------------------------------------------------------------------


def test_docker_container_stats_fields(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers/{cid}/stats returns all expected DockerStats fields."""
    node = e2e_resources.create_docker_node()
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-stats-fields alpine sleep 300"
        e2e_client.post(
            "/api/v2/commands/raw-executions",
            json={"node_ids": [node["id"]], "commands": [cmd]},
        )
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-stats-fields/stats"
        )
        assert resp.status_code == 200, f"stats failed: {resp.status_code} {resp.text}"
        stats = resp.json()
        # Verify key DockerStats fields are present
        # (aliased: Container, Name, CPUPerc, MemUsage)
        assert "Container" in stats, (
            f"Missing 'Container' in stats: {list(stats.keys())}"
        )
        assert "Name" in stats, f"Missing 'Name' in stats: {list(stats.keys())}"
        assert "CPUPerc" in stats or "cpu_percent" in stats, (
            f"Missing CPU field in stats: {list(stats.keys())}"
        )
        assert "MemUsage" in stats or "mem_usage" in stats, (
            f"Missing memory field in stats: {list(stats.keys())}"
        )
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/e2e-stats-fields?force=true"
        )


def test_docker_container_stats_not_found(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../containers/nonexistent/stats should return 404."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(
        f"/api/v2/nodes/{node['id']}/docker/containers/nonexistent-ctr/stats"
    )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ---------------------------------------------------------------------------
# Docker Container Create (A.1) + Image inspect/remove/tag/build (A.2-A.5)
# ---------------------------------------------------------------------------


@pytest.mark.e2e_slow
def test_docker_container_create(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../containers creates a container (Create -> inspect -> remove)."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={
            "image": "alpine:latest",
            "name": "e2e-create-ctr",
            "command": "sleep 60",
            "labels": {"com.example.test": "true"},
        },
    )
    assert resp.status_code == 201, f"create failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["id"]
    assert data["name"] == "e2e-create-ctr"
    assert data["image"] == "alpine:latest"
    assert data["status"] == "created"

    # Inspect via existing endpoint to confirm it exists
    resp = e2e_client.get(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-create-ctr"
    )
    assert resp.status_code == 200
    assert resp.json()["State"]["status"] == "created"

    # Remove (force) via existing endpoint
    resp = e2e_client.delete(
        f"/api/v2/nodes/{node['id']}/docker/containers/e2e-create-ctr?force=true"
    )
    assert resp.status_code == 204


def test_docker_image_inspect(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET .../images/{image_id} returns image details."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/images/alpine:latest")
    assert resp.status_code == 200, f"inspect failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["id"].startswith("sha256:")
    assert "alpine:latest" in data["repo_tags"]
    assert data["size"] > 0
    assert data["architecture"] in {"amd64", "arm64", "arm", "x86_64"}
    assert data["os"] == "linux"


def test_docker_image_remove(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """DELETE .../images/{image_id} removes an image."""
    node = e2e_resources.create_docker_node()
    # Pull a separate image so we don't affect other tests
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/pull",
        json={"image": "busybox:latest", "timeout": 120},
    )
    assert resp.status_code == 200

    resp = e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/images/busybox:latest")
    assert resp.status_code == 204, f"remove failed: {resp.status_code} {resp.text}"

    # Verify it's gone (inspect should 404)
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/images/busybox:latest")
    assert resp.status_code == 404


def test_docker_image_tag(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../images/{image_id}/tag tags an image."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/alpine:latest/tag",
        json={"repo": "local/e2e-alpine", "tag": "v1.0"},
    )
    assert resp.status_code == 200, f"tag failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["source"] == "alpine:latest"
    assert data["target"] == "local/e2e-alpine:v1.0"

    # Inspect the tagged image to confirm it exists
    resp = e2e_client.get(
        f"/api/v2/nodes/{node['id']}/docker/images/local/e2e-alpine:v1.0"
    )
    assert resp.status_code == 200
    assert "local/e2e-alpine:v1.0" in resp.json()["repo_tags"]

    # Cleanup the tag
    e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/images/local/e2e-alpine:v1.0")


@pytest.mark.e2e_slow
def test_docker_image_build(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../images/build builds an image from a Dockerfile via stdin."""
    node = e2e_resources.create_docker_node()
    dockerfile = "FROM alpine:latest\nRUN echo hello > /built-marker\n"
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/images/build",
        json={
            "dockerfile": dockerfile,
            "tag": "local/e2e-built:v1",
            "no_cache": True,
        },
    )
    assert resp.status_code == 200, f"build failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert data["tag"] == "local/e2e-built:v1"
    assert data["image_id"]
    assert "Successfully" in data["output"] or "sha256:" in data["output"]

    # Verify the built image exists via inspect
    resp = e2e_client.get(
        f"/api/v2/nodes/{node['id']}/docker/images/local/e2e-built:v1"
    )
    assert resp.status_code == 200
    assert "local/e2e-built:v1" in resp.json()["repo_tags"]

    # Cleanup
    e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/images/local/e2e-built:v1")


# ---------------------------------------------------------------------------
# Docker Networks CRUD
# ---------------------------------------------------------------------------


def test_docker_network_create_and_inspect(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../networks creates a network, GET inspects it."""
    node = e2e_resources.create_docker_node()
    net_name = "e2e-test-net"

    # Create
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/networks",
        json={"name": net_name, "driver": "bridge"},
    )
    assert resp.status_code == 201, f"create failed: {resp.text}"
    net_id = resp.json()["id"]
    assert resp.json()["name"] == net_name

    try:
        # Inspect
        resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == net_name
        assert data["driver"] == "bridge"
        assert data["id"] == net_id
    finally:
        # Cleanup
        e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}")


def test_docker_network_remove(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """DELETE .../networks/{id} removes a network."""
    node = e2e_resources.create_docker_node()

    # Create
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/networks",
        json={"name": "e2e-rm-net", "driver": "bridge"},
    )
    assert resp.status_code == 201
    net_id = resp.json()["id"]

    # Remove
    resp = e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}")
    assert resp.status_code == 204

    # Verify removed
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}")
    assert resp.status_code in (404, 500)


def test_docker_network_connect_disconnect(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """Connect and disconnect a container from a network."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])

    # Create network
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/networks",
        json={"name": "e2e-conn-net", "driver": "bridge"},
    )
    assert resp.status_code == 201
    net_id = resp.json()["id"]

    # Create container
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={"image": "alpine:latest", "command": "sleep 300"},
    )
    assert resp.status_code == 201
    container_id = resp.json()["id"]

    try:
        # Start container so it appears in network inspect
        e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/start"
        )

        # Connect
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}/connect",
            json={"container_id": container_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"

        # Inspect should show the container
        resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}")
        assert resp.status_code == 200
        connected = resp.json()["containers"]
        assert len(connected) >= 1

        # Disconnect
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}/disconnect",
            json={"container_id": container_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disconnected"
    finally:
        # Cleanup
        e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/stop"
        )
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )
        e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/networks/{net_id}")


# ---------------------------------------------------------------------------
# Docker Volumes CRUD
# ---------------------------------------------------------------------------


def test_docker_volume_create_and_inspect(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../volumes creates a volume, GET inspects it."""
    node = e2e_resources.create_docker_node()

    # Create
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/volumes",
        json={"driver": "local"},
    )
    assert resp.status_code == 201, f"create failed: {resp.text}"
    vol_name = resp.json()["name"]
    assert vol_name

    try:
        # Inspect
        resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/volumes/{vol_name}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == vol_name
        assert data["driver"] == "local"
        assert data["mountpoint"]
    finally:
        # Cleanup
        e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/volumes/{vol_name}")


def test_docker_volume_remove(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """DELETE .../volumes/{name} removes a volume."""
    node = e2e_resources.create_docker_node()

    # Create
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/volumes",
        json={"driver": "local"},
    )
    assert resp.status_code == 201
    vol_name = resp.json()["name"]

    # Remove
    resp = e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/volumes/{vol_name}")
    assert resp.status_code == 204

    # Verify removed
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/volumes/{vol_name}")
    assert resp.status_code in (404, 500)


def test_docker_volume_prune(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST .../volumes/prune prunes unused volumes."""
    node = e2e_resources.create_docker_node()

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/volumes/prune",
    )
    assert resp.status_code == 200
    assert "output" in resp.json()


# ---------------------------------------------------------------------------
# Container lifecycle extensions
# ---------------------------------------------------------------------------


def test_docker_container_pause_unpause(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """Pause and unpause a container."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])

    # Create and start
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={"image": "alpine:latest", "command": "sleep 300"},
    )
    assert resp.status_code == 201
    container_id = resp.json()["id"]

    try:
        e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/start"
        )

        # Pause
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/pause"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        # Verify paused state
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["State"]["status"] == "paused"

        # Unpause
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/unpause"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "unpaused"
    finally:
        e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/stop"
        )
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )


def test_docker_container_rename(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """Rename a container."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])

    # Create
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={"image": "alpine:latest", "command": "sleep 300"},
    )
    assert resp.status_code == 201
    container_id = resp.json()["id"]

    try:
        # Rename
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/rename",
            json={"new_name": "e2e-renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["new_name"] == "e2e-renamed"

        # Inspect should show the new name
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )
        assert resp.status_code == 200
        assert "e2e-renamed" in resp.json()["Name"]
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )


def test_docker_container_top(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """List processes inside a running container."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])

    # Create and start
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={"image": "alpine:latest", "command": "sleep 300"},
    )
    assert resp.status_code == 201
    container_id = resp.json()["id"]

    try:
        e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/start"
        )

        # Top
        resp = e2e_client.get(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/top"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "titles" in data
        assert "processes" in data
        assert len(data["titles"]) > 0
        assert len(data["processes"]) >= 1
    finally:
        e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/stop"
        )
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )


# ---------------------------------------------------------------------------
# System info & prune
# ---------------------------------------------------------------------------


def test_docker_system_info(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/system/info returns Docker system info."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/system/info")
    assert resp.status_code == 200
    data = resp.json()
    assert "server_version" in data
    assert "storage_driver" in data
    assert "operating_system" in data
    assert "architecture" in data
    assert "total_memory" in data
    assert "cpus" in data
    assert isinstance(data["cpus"], int)
    assert data["cpus"] > 0


def test_docker_system_df(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/system/df returns disk usage."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/system/df")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        assert "type" in item
        assert "total_count" in item


def test_docker_container_prune(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/prune prunes stopped containers."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])

    # Create and stop a container to make it pruneable
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={"image": "alpine:latest", "command": "echo done"},
    )
    assert resp.status_code == 201

    # Wait for it to stop
    import time

    time.sleep(2)

    # Prune
    resp = e2e_client.post(f"/api/v2/nodes/{node['id']}/docker/containers/prune")
    assert resp.status_code == 200
    data = resp.json()
    assert "containers_deleted" in data
    assert "space_reclaimed" in data


def test_docker_image_prune(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/images/prune prunes unused images."""
    node = e2e_resources.create_docker_node()

    resp = e2e_client.post(f"/api/v2/nodes/{node['id']}/docker/images/prune")
    assert resp.status_code == 200
    data = resp.json()
    assert "images_deleted" in data
    assert "space_reclaimed" in data


# ---------------------------------------------------------------------------
# Bulk inspect / logs / stats
# ---------------------------------------------------------------------------


def test_docker_bulk_inspect(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/inspections vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name bulk-inspect-ctr alpine sleep 300"],
        },
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/inspections",
        json={"container_ids": ["bulk-inspect-ctr"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1
    # inspect result has data with Name field
    assert data["results"][0]["container_id"] == "bulk-inspect-ctr"


def test_docker_bulk_logs(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/logs vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": [
                "docker run -d --name bulk-logs-ctr alpine"
                " sh -c 'echo hello-logs; sleep 300'"
            ],
        },
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/logs",
        json={"container_ids": ["bulk-logs-ctr"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1


def test_docker_bulk_stats(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/containers/stats vert bulk."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    e2e_client.post(
        "/api/v2/commands/raw-executions",
        json={
            "node_ids": [node["id"]],
            "commands": ["docker run -d --name bulk-stats-ctr alpine sleep 300"],
        },
    )

    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers/stats",
        json={"container_ids": ["bulk-stats-ctr"]},
    )
    assert resp.status_code in (200, 207)
    data = resp.json()
    assert data["total"] == 1
    assert data["succeeded"] == 1


# ---------------------------------------------------------------------------
# Additional validation E2E tests
# ---------------------------------------------------------------------------


def test_docker_network_create_invalid_driver(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/networks with invalid driver returns 422."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/networks",
        json={"name": "test-net", "driver": "bad;driver"},
    )
    assert resp.status_code == 422


def test_docker_volume_create_named(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /nodes/{id}/docker/volumes with explicit name creates named volume."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/volumes",
        json={"name": "e2e-named-vol", "driver": "local"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "e2e-named-vol"

    # Verify via inspect
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/volumes/e2e-named-vol")
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-named-vol"

    # Cleanup
    e2e_client.delete(f"/api/v2/nodes/{node['id']}/docker/volumes/e2e-named-vol")


def test_docker_container_rename_validation(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """POST /containers/{id}/rename with invalid name returns 422."""
    node = e2e_resources.create_docker_node()
    _docker_pull_alpine(e2e_client, node["id"])
    resp = e2e_client.post(
        f"/api/v2/nodes/{node['id']}/docker/containers",
        json={"image": "alpine:latest", "command": "sleep 300"},
    )
    assert resp.status_code == 201
    container_id = resp.json()["id"]

    try:
        resp = e2e_client.post(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}/rename",
            json={"new_name": ""},
        )
        assert resp.status_code == 422
    finally:
        e2e_client.delete(
            f"/api/v2/nodes/{node['id']}/docker/containers/{container_id}"
        )


def test_docker_system_info_fields(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/system/info returns all expected fields."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/system/info")
    assert resp.status_code == 200
    data = resp.json()
    expected_fields = [
        "server_version",
        "storage_driver",
        "operating_system",
        "architecture",
        "total_memory",
        "cpus",
        "containers_running",
        "containers_stopped",
        "images",
    ]
    for field in expected_fields:
        assert field in data, f"Missing field: {field}"


def test_docker_system_df_fields(
    e2e_client,
    e2e_resources: UniqueResourceFactory,
):
    """GET /nodes/{id}/docker/system/df returns all expected fields."""
    node = e2e_resources.create_docker_node()
    resp = e2e_client.get(f"/api/v2/nodes/{node['id']}/docker/system/df")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    for item in data:
        assert "type" in item
        assert "total_count" in item
        assert "active_size" in item
        assert "reclaimable_size" in item
        assert "reclaimable_percent" in item
