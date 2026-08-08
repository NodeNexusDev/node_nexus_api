"""Shared node and audit helpers used across multiple E2E test files."""

import time

import httpx2 as httpx

_NODE_PAYLOAD = {
    "name": "e2e-node",
    "host": "10.0.0.1",
    "port": 22,
    "connection_type": "ssh",
}


def create_node(e2e_client: httpx.Client, **overrides: object) -> dict:
    """Create a basic node for tests."""
    data = {**_NODE_PAYLOAD, **overrides}
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


def create_ssh_node(
    e2e_client: httpx.Client,
    *,
    name: str = "ssh-node",
    host: str = "ssh-server",
    port: int = 2222,
    **overrides: object,
) -> dict:
    """Create an SSH node connected to the test SSH server.

    Uses Docker compose service name "ssh-server" as host by default.
    For tests that need to connect via mapped ports, pass host/port explicitly.
    """
    data: dict[str, object] = {
        "name": name,
        "host": host,
        "port": port,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }
    data.update(overrides)
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


def create_docker_node(
    e2e_client: httpx.Client,
    *,
    name: str = "docker-node",
    **overrides: object,
) -> dict:
    """Create a Docker node pointing to the internal DinD service."""
    data: dict[str, object] = {
        "name": name,
        "host": "ssh-server",
        "port": 2222,
        "connection_type": "docker",
        "username": "testuser",
        "password": "testpass",
        "docker_host": "tcp://dind:2375",
    }
    data.update(overrides)
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


def wait_for_audit(
    client: httpx.Client,
    *,
    query: str = "",
    action: str | None = None,
    node_id: str | None = None,
    minimum_total: int = 1,
    timeout: float = 10.0,
) -> dict:
    """Poll the eventually-consistent transactional outbox.

    Never filters by *action* server-side — fetches all records (optionally
    scoped to *node_id*) and checks *action* locally so ``data["total"]``
    reflects the full count the caller expects.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        params: dict[str, str | int] = {"page": 1, "size": 100}
        if node_id:
            params["node_id"] = node_id
        if query:
            response = client.get(f"/api/v1/audit/{query}", params=params)
        else:
            response = client.get("/api/v1/audit/", params=params)
        assert response.status_code == 200
        data = response.json()
        if data["total"] >= minimum_total:
            items = data["items"]
            if action is None or any(i["action"] == action for i in items):
                return data
        time.sleep(0.2)
    raise AssertionError(
        f"audit event was not delivered: action={action}, query={query}"
    )
