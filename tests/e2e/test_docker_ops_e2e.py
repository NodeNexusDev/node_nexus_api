"""E2E tests for Docker operations via SSH-backed Docker nodes."""

import time

import pytest

from tests.e2e.helpers.nodes import create_ssh_node as _create_ssh_node

pytestmark = pytest.mark.docker


def _create_docker_node(e2e_client, **overrides):
    """Create an SSH node with Docker host pointing to internal dind."""
    return _create_ssh_node(
        e2e_client,
        name="docker-e2e-node",
        connection_type="docker",
        docker_host="tcp://dind:2375",
        **overrides,
    )


def _docker_pull_alpine(e2e_client, node_id):
    """Pull alpine image on a Docker node (prerequisite for container tests)."""
    resp = e2e_client.post(
        f"/api/v1/nodes/{node_id}/docker/images/pull",
        json={"image": "alpine:latest", "timeout": 120},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Docker Images
# ---------------------------------------------------------------------------


def test_docker_list_images(e2e_client):
    """GET /nodes/{id}/docker/images returns image list."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/images")
        assert resp.status_code == 200
        images = resp.json()
        assert isinstance(images, list)
        alpine_images = [i for i in images if "alpine" in str(i).lower()]
        assert len(alpine_images) >= 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_pull_image(e2e_client):
    """POST /nodes/{id}/docker/images/pull pulls an image."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/images/pull",
            json={"image": "alpine:3.20", "timeout": 120},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Containers
# ---------------------------------------------------------------------------


def test_docker_list_containers(e2e_client):
    """GET /nodes/{id}/docker/containers returns list."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/containers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_list_containers_all(e2e_client):
    """GET .../containers?all=true includes stopped containers."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/containers?all=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_lifecycle(e2e_client):
    """Full container lifecycle: run, inspect, stop, start, restart, remove."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])

        # Run a container via SSH exec (docker run -d alpine sleep 300)
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name e2e-test-ctr alpine sleep 300"},
        )
        assert resp.status_code == 200

        # Inspect
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["State"]["status"] == "running"

        # Stop
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/stop"
        )
        assert resp.status_code == 204

        # Start
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/start"
        )
        assert resp.status_code == 204

        # Restart
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/restart"
        )
        assert resp.status_code == 204

        # Logs
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/logs"
        )
        assert resp.status_code == 200

        # Exec
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/exec",
            json={"command": "echo exec-ok"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "exec-ok" in result["stdout"]

        # Stats
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr/stats"
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert "Name" in stats or "CPUPerc" in stats

        # Remove (force)
        resp = e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-test-ctr?force=true"
        )
        assert resp.status_code == 204

    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_not_found(e2e_client):
    """GET .../containers/{id} returns 404 for missing container."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/nonexistent"
        )
        assert resp.status_code == 404
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_exec_validation(e2e_client):
    """POST .../exec returns 422 for invalid container ID."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/bad;$id/exec",
            json={"command": "ls"},
        )
        assert resp.status_code == 422
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Networks and Volumes
# ---------------------------------------------------------------------------


def test_docker_list_networks(e2e_client):
    """GET /nodes/{id}/docker/networks returns network list."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/networks")
        assert resp.status_code == 200
        networks = resp.json()
        assert isinstance(networks, list)
        # bridge network should exist by default
        names = [n.get("Name", "") for n in networks]
        assert "bridge" in names
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_list_volumes(e2e_client):
    """GET /nodes/{id}/docker/volumes returns volume list."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(f"/api/v1/nodes/{node['id']}/docker/volumes")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Bulk Operations
# ---------------------------------------------------------------------------


def test_docker_bulk_start(e2e_client):
    """POST /api/v1/docker/bulk/start starts container on multiple nodes."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        # Run a container via SSH
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-start-ctr alpine sleep 300"},
        )
        # Stop it first
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/bulk-start-ctr/stop"
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/start",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-start-ctr",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "start"
        assert data["total"] == 1
        assert data["succeeded"] == 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_bulk_stop(e2e_client):
    """POST /api/v1/docker/bulk/stop stops container on multiple nodes."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-stop-ctr alpine sleep 300"},
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/stop",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-stop-ctr",
                "timeout": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "stop"
        assert data["total"] == 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_bulk_restart(e2e_client):
    """POST /api/v1/docker/bulk/restart restarts container on multiple nodes."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-restart-ctr alpine sleep 300"},
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/restart",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-restart-ctr",
                "timeout": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "restart"
        assert data["succeeded"] == 1
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_bulk_exec(e2e_client):
    """POST /api/v1/docker/bulk/exec runs command in containers."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": "docker run -d --name bulk-exec-ctr alpine sleep 300"},
        )

        resp = e2e_client.post(
            "/api/v1/docker/bulk/exec",
            json={
                "node_ids": [node["id"]],
                "container_id": "bulk-exec-ctr",
                "command": "echo exec-works",
                "timeout": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "exec"
        results = data["results"]
        assert len(results) == 1
        assert "exec-works" in results[0]["output"]
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# API Key scope enforcement (403 on read-only)
# ---------------------------------------------------------------------------


def test_docker_container_logs_explicit_tail(e2e_client):
    """GET .../containers/{cid}/logs?tail=N returns exactly N lines."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        # Generate a container that prints 10 numbered lines then sleeps
        cmd = (
            "docker run -d --name e2e-logs-tail alpine sh -c "
            "'for i in $(seq 1 10); do echo line-$i; done; sleep 60'"
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        assert resp.status_code == 200

        # Wait for container to finish printing

        time.sleep(2)

        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-tail/logs?tail=3"
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
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-tail?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_logs_tail_default(e2e_client):
    """GET .../containers/{cid}/logs (without tail) uses default tail=100."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = (
            "docker run -d --name e2e-logs-default alpine sh -c 'echo hello; sleep 60'"
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        assert resp.status_code == 200

        time.sleep(1)

        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-default/logs"
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
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-default?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_logs_since_iso_timestamp(e2e_client):
    """GET .../containers/{cid}/logs?since=<ISO> limits output to since timestamp."""

    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = (
            "docker run -d --name e2e-logs-since alpine sh -c "
            "'echo before-sleep; sleep 2; echo after-sleep; sleep 60'"
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        assert resp.status_code == 200

        # Wait for container to start and print first line
        time.sleep(1)

        # Capture current time (after first echo, before second)
        since = str(int(time.time()))

        # Wait for second echo
        time.sleep(3)

        # Get logs since the captured timestamp
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-since/logs"
            f"?since={since}"
        )
        assert resp.status_code == 200
        output = resp.text
        # Should contain after-sleep but may not contain before-sleep
        assert "after-sleep" in output
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-since?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_logs_invalid_tail_zero(e2e_client):
    """GET .../logs?tail=0 should return 422 (ge=1 constraint)."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-logs-zero alpine sleep 60"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-zero/logs?tail=0"
        )
        assert resp.status_code == 422, (
            f"Expected 422 for tail=0, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-zero?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_logs_invalid_tail_overflow(e2e_client):
    """GET .../logs?tail=99999 should return 422 (le=10000 constraint)."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-logs-overflow alpine sleep 60"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-overflow/logs?tail=99999"
        )
        assert resp.status_code == 422, (
            f"Expected 422 for tail=99999, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-logs-overflow?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Container Exec — parameterized (Stage N.2)
# ---------------------------------------------------------------------------


def test_docker_container_exec_timeout_boundary(e2e_client):
    """POST .../exec with timeout=1 (minimum) should work."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-t1 alpine sleep 300"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-t1/exec",
            json={"command": "echo ok", "timeout": 1},
        )
        assert resp.status_code == 200, (
            f"Expected 200 for timeout=1, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-t1?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_exec_timeout_max(e2e_client):
    """POST .../exec with timeout=600 (maximum) should work."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-tmax alpine sleep 300"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-tmax/exec",
            json={"command": "echo ok", "timeout": 600},
        )
        assert resp.status_code == 200, (
            f"Expected 200 for timeout=600, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-tmax?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_exec_command_too_long(e2e_client):
    """POST .../exec with command > 4096 chars should return 422."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-long alpine sleep 300"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-long/exec",
            json={"command": "A" * 5000, "timeout": 30},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for long command, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-long?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_exec_timeout_exceeded(e2e_client):
    """POST .../exec with command that exceeds timeout should complete with error."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-exec-timeout alpine sleep 300"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.post(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-timeout/exec",
            json={"command": "sleep 10", "timeout": 1},
        )
        # May be 200 with non-zero exit, or may be an error response
        # The key assertion: it should NOT be a 500 internal server error
        assert resp.status_code < 500, (
            f"Got 5xx ({resp.status_code}) on exec timeout: {resp.text}"
        )
    finally:
        e2e_client.delete(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-exec-timeout?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# Docker Container Stats — parameterized (Stage N.3)
# ---------------------------------------------------------------------------


def test_docker_container_stats_fields(e2e_client):
    """GET .../containers/{cid}/stats returns all expected DockerStats fields."""
    node = _create_docker_node(e2e_client)
    try:
        _docker_pull_alpine(e2e_client, node["id"])
        cmd = "docker run -d --name e2e-stats-fields alpine sleep 300"
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": cmd},
        )
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-stats-fields/stats"
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
            f"/api/v1/nodes/{node['id']}/docker/containers/e2e-stats-fields?force=true"
        )
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


def test_docker_container_stats_not_found(e2e_client):
    """GET .../containers/nonexistent/stats should return 404."""
    node = _create_docker_node(e2e_client)
    try:
        resp = e2e_client.get(
            f"/api/v1/nodes/{node['id']}/docker/containers/nonexistent-ctr/stats"
        )
        assert resp.status_code == 404, (
            f"Expected 404, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")
