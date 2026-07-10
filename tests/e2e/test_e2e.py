"""E2E tests for the full application stack."""

import httpx

from tests.e2e.conftest import ServicePorts


def test_health(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


def test_crud_full_cycle(e2e_client: httpx.Client) -> None:
    # Create
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "e2e-node",
            "host": "10.0.0.1",
            "port": 22,
            "connection_type": "ssh",
        },
    )
    assert resp.status_code == 201
    node = resp.json()
    node_id = node["id"]
    assert node["name"] == "e2e-node"
    assert node["status"] == "active"

    # Read
    resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-node"

    # Read all
    resp = e2e_client.get("/api/v1/nodes/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # Update
    resp = e2e_client.put(
        f"/api/v1/nodes/{node_id}",
        json={"name": "e2e-node-updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-node-updated"

    # Delete
    resp = e2e_client.delete(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = e2e_client.get(f"/api/v1/nodes/{node_id}")
    assert resp.status_code == 404


def test_create_with_credentials(
    e2e_client: httpx.Client, service_ports: ServicePorts
) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "ssh-node",
            "host": service_ports.ssh_host,
            "port": service_ports.ssh_port,
            "connection_type": "ssh",
            "username": "testuser",
            "password": "testpass",
        },
    )
    assert resp.status_code == 201
    node = resp.json()
    assert node["name"] == "ssh-node"
    assert node["username"] == "testuser"
    # Secrets must NOT be in response
    assert "password" not in node
    assert "ssh_key" not in node


def test_validation_error(e2e_client: httpx.Client) -> None:
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={"name": "incomplete"},
    )
    assert resp.status_code == 422


def test_not_found_errors(e2e_client: httpx.Client) -> None:
    import uuid

    fake_id = str(uuid.uuid4())

    resp = e2e_client.get(f"/api/v1/nodes/{fake_id}")
    assert resp.status_code == 404

    resp = e2e_client.put(
        f"/api/v1/nodes/{fake_id}",
        json={"name": "x"},
    )
    assert resp.status_code == 404

    resp = e2e_client.delete(f"/api/v1/nodes/{fake_id}")
    assert resp.status_code == 404


def test_ssh_check_connectivity(e2e_client: httpx.Client) -> None:
    # Create node pointing to SSH server (internal Docker hostname)
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "ssh-test",
            "host": "ssh-server",
            "port": 2222,
            "connection_type": "ssh",
            "username": "testuser",
            "password": "testpass",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    # Check connectivity
    resp = e2e_client.post(f"/api/v1/nodes/{node_id}/check")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_ssh_execute_command(e2e_client: httpx.Client) -> None:
    # Create node
    resp = e2e_client.post(
        "/api/v1/nodes/",
        json={
            "name": "ssh-exec",
            "host": "ssh-server",
            "port": 2222,
            "connection_type": "ssh",
            "username": "testuser",
            "password": "testpass",
        },
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    # Execute command
    resp = e2e_client.post(
        f"/api/v1/nodes/{node_id}/execute",
        json={"command": "echo e2e-works"},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["stdout"].strip() == "e2e-works"
    assert result["exit_code"] == 0


def test_ssh_check_not_found(e2e_client: httpx.Client) -> None:
    import uuid

    resp = e2e_client.post(f"/api/v1/nodes/{uuid.uuid4()}/check")
    assert resp.status_code == 404


def test_ssh_execute_not_found(e2e_client: httpx.Client) -> None:
    import uuid

    resp = e2e_client.post(
        f"/api/v1/nodes/{uuid.uuid4()}/execute",
        json={"command": "ls"},
    )
    assert resp.status_code == 404
