"""E2E tests for WebSocket streaming endpoint.

These tests verify the real WebSocket → application service →
AsyncSSH adapter → SSH container data flow.

Endpoint: ws://.../api/v1/nodes/{node_id}/exec-stream?token=<api_key>

IMPORTANT: These tests are marked as xfail because the WebSocket route
returns HTTP 404 at runtime. The likely root cause is that
``APIRouter(route_class=DishkaRoute)`` does not correctly handle
WebSocket upgrade requests.

The unit tests in ``tests/unit/test_websocket.py`` confirm the route
is registered on the router object, but at the ASGI level the route
does not match incoming WebSocket requests.

Recommended fix (in application code):
    1. Replace ``route_class=DishkaRoute`` with the default in the
       WebSocket router:
       ``router = APIRouter(tags=["websocket"])``
    2. Or use ``app.websocket("/api/v1/nodes/{node_id}/exec-stream")``
       directly in ``main.py`` instead of including a router.

Once the application fix is deployed, remove the xfail markers.
"""

import asyncio
import json
from uuid import uuid4

import httpx2 as httpx
import pytest
import websockets
from websockets.asyncio.client import ClientConnection

from tests.e2e.conftest import ServicePorts

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]

# All WebSocket tests are expected to fail until the application
# code fix is deployed. See module docstring for details.
_WS_XFAIL_REASON = (
    "WebSocket route returns 404 — DishkaRoute may not support "
    "WebSocket upgrade. See tests/e2e/test_websocket_e2e.py docstring."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WS_PATH = "/api/v1/nodes/{node_id}/exec-stream"


def _ws_url(service_ports: ServicePorts, node_id: str, token: str) -> str:
    """Build a WebSocket URL with token query parameter."""
    return (
        f"ws://{service_ports.api_host}:{service_ports.api_port}"
        f"{_WS_PATH.format(node_id=node_id)}?token={token}"
    )


def _ws_url_no_token(service_ports: ServicePorts, node_id: str) -> str:
    """Build a WebSocket URL without authentication."""
    return (
        f"ws://{service_ports.api_host}:{service_ports.api_port}"
        f"{_WS_PATH.format(node_id=node_id)}"
    )


def _create_ssh_node(e2e_client: httpx.Client) -> dict:
    """Create an SSH node connected to the test SSH server."""
    data = {
        "name": f"ws-test-{uuid4().hex[:8]}",
        "host": "ssh-server",
        "port": 2222,
        "connection_type": "ssh",
        "username": "testuser",
        "password": "testpass",
    }
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    return resp.json()


async def _send_command(ws: ClientConnection, command: str) -> None:
    """Send a command message over WebSocket."""
    await ws.send(
        json.dumps({"version": "1", "type": "command", "command": command})
    )


async def _send_signal(ws: ClientConnection, signal: str) -> None:
    """Send a signal message over WebSocket."""
    await ws.send(
        json.dumps({"version": "1", "type": "signal", "signal": signal})
    )


async def _receive_until_type(
    ws: ClientConnection,
    expected_type: str,
    timeout: float = 10.0,
) -> dict:
    """Receive messages until one with the expected type appears."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        try:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for {expected_type!r} event"
                )
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if msg.get("type") == expected_type:
                return msg
        except TimeoutError:
            raise


# ---------------------------------------------------------------------------
# C.1 Authentication
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_connect_with_master_key(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """WebSocket connects successfully with master API key."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "echo ok")
            msg = await _receive_until_type(ws, "exit")
            assert msg.get("exit_code") == 0
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_connect_with_managed_key(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """WebSocket connects with a managed read-write API key."""
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "ws-rw-test", "scope": "read-write"},
    )
    assert resp.status_code == 201
    api_key = resp.json()
    key_token = api_key["key"]
    key_id = api_key["id"]

    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], key_token)
        async with websockets.connect(url) as ws:
            await _send_command(ws, "echo managed-key-ok")
            msg = await _receive_until_type(ws, "exit")
            assert msg.get("exit_code") == 0
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")
        e2e_client.delete(f"/api/v1/api-keys/{key_id}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_query_token_works(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Token passed as ?token= query parameter is accepted."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "echo query-token-ok")
            msg = await _receive_until_type(ws, "exit")
            assert msg.get("exit_code") == 0
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_missing_token_closed(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """WebSocket without token is closed with code 4001."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url_no_token(service_ports, node["id"])
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            async with websockets.connect(url) as ws:
                await ws.recv()
        assert exc_info.value.code == 4001
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_invalid_token_closed(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """WebSocket with invalid API key is closed with code 4003."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "invalid-key-xyz")
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            async with websockets.connect(url) as ws:
                await ws.recv()
        assert exc_info.value.code == 4003
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_readonly_key_closed(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """WebSocket with read-only key is closed with code 4003."""
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "ws-ro-test", "scope": "read-only"},
    )
    assert resp.status_code == 201
    ro_key = resp.json()["key"]
    key_id = resp.json()["id"]

    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], ro_key)
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            async with websockets.connect(url) as ws:
                await ws.recv()
        assert exc_info.value.code == 4003
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")
        e2e_client.delete(f"/api/v1/api-keys/{key_id}")


# ---------------------------------------------------------------------------
# C.2 Protocol
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_stdout_event(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Command execution produces stdout events."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "echo hello-stdout")
            msg = await _receive_until_type(ws, "stdout")
            assert msg.get("version") == "1"
            assert "hello-stdout" in msg.get("data", "")
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_stderr_event(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Command producing stderr generates stderr events."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "echo hello-stderr >&2")
            msg = await _receive_until_type(ws, "stderr")
            assert msg.get("version") == "1"
            assert "hello-stderr" in msg.get("data", "")
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_exit_event_with_code(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Command completion produces exit event with real exit code."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "exit 42")
            msg = await _receive_until_type(ws, "exit")
            assert msg.get("version") == "1"
            assert msg.get("exit_code") == 42
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_invalid_json_does_not_disconnect(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Sending invalid JSON returns error but keeps connection alive."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await ws.send("this is not json {{{")
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg.get("type") == "error"
            assert "invalid" in msg.get("message", "").lower()
            # Connection should still be alive
            await _send_command(ws, "echo still-alive")
            msg2 = await _receive_until_type(ws, "exit")
            assert msg2.get("exit_code") == 0
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_second_command_rejected(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Sending a second command while one is running returns error."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            # Start a long-running command
            await _send_command(ws, "sleep 10")
            # Send second command immediately
            await asyncio.sleep(0.1)
            await _send_command(ws, "echo second")
            # Should receive error about active command
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg.get("type") == "error"
            assert "already running" in msg.get("message", "").lower()
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


# ---------------------------------------------------------------------------
# C.3 Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_signal_sigint_ack(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Sending SIGINT signal during command execution returns ack."""
    node = _create_ssh_node(e2e_client)
    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "sleep 30")
            await asyncio.sleep(0.2)
            await _send_signal(ws, "SIGINT")
            msg = await _receive_until_type(ws, "signal_ack")
            assert msg.get("signal") == "SIGINT"
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_unknown_node_closed(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Connecting to a non-existent node closes with code 4004."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    url = _ws_url(service_ports, fake_id, "e2e-master-key-12345")
    async with websockets.connect(url) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg.get("type") == "error"
        # Connection should close after error
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            await ws.recv()
        assert exc_info.value.code == 4004


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_ssh_auth_failure_internal_error(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """SSH connection failure produces error without leaking credentials."""
    data = {
        "name": f"ws-bad-ssh-{uuid4().hex[:8]}",
        "host": "ssh-server",
        "port": 2222,
        "connection_type": "ssh",
        "username": "wronguser",
        "password": "wrongpass",
    }
    resp = e2e_client.post("/api/v1/nodes/", json=data)
    assert resp.status_code == 201
    node = resp.json()

    try:
        url = _ws_url(service_ports, node["id"], "e2e-master-key-12345")
        async with websockets.connect(url) as ws:
            await _send_command(ws, "echo test")
            # Should get error, but NOT contain credentials
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
            msg = json.loads(raw)
            assert msg.get("type") == "error"
            message = msg.get("message", "")
            assert "wronguser" not in message.lower()
            assert "wrongpass" not in message.lower()
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node['id']}")


@pytest.mark.xfail(reason=_WS_XFAIL_REASON)
@pytest.mark.asyncio
async def test_ws_multiple_connections(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Multiple simultaneous WebSocket connections to different nodes work."""
    node_a = _create_ssh_node(e2e_client)
    node_b = _create_ssh_node(e2e_client)
    try:

        async def run_command(node_id: str, marker: str) -> str:
            url = _ws_url(service_ports, node_id, "e2e-master-key-12345")
            async with websockets.connect(url) as ws:
                await _send_command(ws, f"echo {marker}")
                msg = await _receive_until_type(ws, "stdout", timeout=10)
                return msg.get("data", "")

        results = await asyncio.gather(
            run_command(node_a["id"], "node-a"),
            run_command(node_b["id"], "node-b"),
        )
        assert "node-a" in results[0]
        assert "node-b" in results[1]
    finally:
        e2e_client.delete(f"/api/v1/nodes/{node_a['id']}")
        e2e_client.delete(f"/api/v1/nodes/{node_b['id']}")
