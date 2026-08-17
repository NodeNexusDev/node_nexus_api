"""E2E tests for WebSocket streaming endpoint.

These tests verify the real WebSocket → application service →
AsyncSSH adapter → SSH container data flow.

Endpoint: ws://.../api/v1/nodes/{node_id}/exec-stream
Authentication: x-api-key header

The WebSocket router uses Dishka's explicit ``@inject`` integration because
``DishkaRoute`` only supports automatic injection for HTTP routes.
"""

import asyncio
import json
from uuid import uuid4

import httpx2 as httpx
import pytest
import websockets
from websockets.asyncio.client import ClientConnection

from tests.e2e.conftest import ServicePorts
from tests.e2e.helpers.resources import UniqueResourceFactory
from tests.e2e.helpers.websocket import WebSocketClientFactory

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WS_PATH = "/api/v1/nodes/{node_id}/exec-stream"


def _close_code(exc: websockets.exceptions.ConnectionClosed) -> int | None:
    """Return the received close frame code, tolerating missing close frames.

    ``ConnectionClosed.code`` is deprecated since websockets 13.1. We read the
    received close code instead, falling back to the sent code when the remote
    endpoint dropped the connection without a close frame (``rcvd is None``).
    """
    if exc.rcvd is not None:
        return exc.rcvd.code
    if exc.sent is not None:
        return exc.sent.code
    return None


def _ws_url(service_ports: ServicePorts, node_id: str) -> str:
    """Build a WebSocket URL without token (use header for auth)."""
    return (
        f"ws://{service_ports.api_host}:{service_ports.api_port}"
        f"{_WS_PATH.format(node_id=node_id)}"
    )


def _ws_url_no_token(service_ports: ServicePorts, node_id: str) -> str:
    """Build a WebSocket URL without authentication."""
    return (
        f"ws://{service_ports.api_host}:{service_ports.api_port}"
        f"{_WS_PATH.format(node_id=node_id)}"
    )


async def _send_command(ws: ClientConnection, command: str) -> None:
    """Send a command message over WebSocket."""
    await ws.send(json.dumps({"version": "1", "type": "command", "command": command}))


async def _send_signal(ws: ClientConnection, signal: str) -> None:
    """Send a signal message over WebSocket."""
    await ws.send(json.dumps({"version": "1", "type": "signal", "signal": signal}))


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
                raise TimeoutError(f"Timed out waiting for {expected_type!r} event")
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if msg.get("type") == expected_type:
                return msg
        except TimeoutError:
            raise


# ---------------------------------------------------------------------------
# C.1 Authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_connect_with_master_key(
    websocket_client: WebSocketClientFactory,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """WebSocket connects with the master key in the X-API-Key header."""
    node = e2e_resources.create_ssh_node()
    path = _WS_PATH.format(node_id=node["id"])
    async with websocket_client.connect_with_header(
        path,
        "e2e-master-key-12345",
    ) as ws:
        await _send_command(ws, "echo header-auth-ok")
        msg = await _receive_until_type(ws, "exit")
        assert msg.get("exit_code") == 0


@pytest.mark.asyncio
async def test_ws_connect_with_managed_key(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
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

    node = e2e_resources.create_ssh_node()
    try:
        url = _ws_url(service_ports, node["id"])
        async with websockets.connect(
            url, additional_headers={"x-api-key": key_token}
        ) as ws:
            await _send_command(ws, "echo managed-key-ok")
            msg = await _receive_until_type(ws, "exit")
            assert msg.get("exit_code") == 0
    finally:
        e2e_client.delete(f"/api/v1/api-keys/{key_id}")


@pytest.mark.asyncio
async def test_ws_query_token_rejected(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Token passed as ?token= query parameter is no longer accepted."""
    node = e2e_resources.create_ssh_node()
    url = f"{_ws_url(service_ports, node['id'])}?token=e2e-master-key-12345"
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
        async with websockets.connect(url) as ws:
            await ws.recv()
    assert _close_code(exc_info.value) == 4001


@pytest.mark.asyncio
async def test_ws_missing_token_closed(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """WebSocket without token is closed with code 4001."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url_no_token(service_ports, node["id"])
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
        async with websockets.connect(url) as ws:
            await ws.recv()
    assert _close_code(exc_info.value) == 4001


@pytest.mark.asyncio
async def test_ws_invalid_token_closed(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """WebSocket with invalid API key is closed with code 4003."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
        async with websockets.connect(
            url, additional_headers={"x-api-key": "invalid-key-xyz"}
        ) as ws:
            await ws.recv()
    assert _close_code(exc_info.value) == 4003


@pytest.mark.parametrize("credential_state", ["revoked", "expired"])
@pytest.mark.asyncio
async def test_ws_inactive_managed_key_closed(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
    credential_state: str,
) -> None:
    """Revoked and expired managed keys are closed with code 4003."""
    api_key = e2e_resources.create_api_key()
    node = e2e_resources.create_ssh_node()
    if credential_state == "revoked":
        response = e2e_client.delete(f"/api/v1/api-keys/{api_key['id']}")
        assert response.status_code == 204, response.text
    else:
        response = e2e_client.patch(
            f"/api/v1/api-keys/{api_key['id']}",
            json={"expires_at": "2000-01-01T00:00:00Z"},
        )
        assert response.status_code == 200, response.text

    url = _ws_url(service_ports, node["id"])
    with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
        async with websockets.connect(
            url, additional_headers={"x-api-key": api_key["key"]}
        ) as ws:
            await ws.recv()
    assert _close_code(exc_info.value) == 4003


@pytest.mark.asyncio
async def test_ws_readonly_key_closed(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """WebSocket with read-only key is closed with code 4003."""
    resp = e2e_client.post(
        "/api/v1/api-keys/",
        json={"name": "ws-ro-test", "scope": "read-only"},
    )
    assert resp.status_code == 201
    ro_key = resp.json()["key"]
    key_id = resp.json()["id"]

    node = e2e_resources.create_ssh_node()
    try:
        url = _ws_url(service_ports, node["id"])
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            async with websockets.connect(
                url, additional_headers={"x-api-key": ro_key}
            ) as ws:
                await ws.recv()
        assert _close_code(exc_info.value) == 4003
    finally:
        e2e_client.delete(f"/api/v1/api-keys/{key_id}")


# ---------------------------------------------------------------------------
# C.2 Protocol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_stdout_event(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Command execution produces stdout events."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await _send_command(ws, "echo hello-stdout")
        msg = await _receive_until_type(ws, "stdout")
        assert msg.get("version") == "1"
        assert "hello-stdout" in msg.get("data", "")


@pytest.mark.asyncio
async def test_ws_stderr_event(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Command producing stderr generates stderr events."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await _send_command(ws, "echo hello-stderr >&2")
        msg = await _receive_until_type(ws, "stderr")
        assert msg.get("version") == "1"
        assert "hello-stderr" in msg.get("data", "")


@pytest.mark.asyncio
async def test_ws_exit_event_with_code(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Command completion produces exit event with real exit code."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await _send_command(ws, "exit 42")
        msg = await _receive_until_type(ws, "exit")
        assert msg.get("version") == "1"
        assert msg.get("exit_code") == 42


@pytest.mark.asyncio
async def test_ws_invalid_json_does_not_disconnect(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Sending invalid JSON returns error but keeps connection alive."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await ws.send("this is not json {{{")
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg.get("type") == "error"
        assert "invalid" in msg.get("message", "").lower()
        # Connection should still be alive
        await _send_command(ws, "echo still-alive")
        msg2 = await _receive_until_type(ws, "exit")
        assert msg2.get("exit_code") == 0


@pytest.mark.asyncio
async def test_ws_invalid_command_does_not_disconnect(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Invalid command messages return an error and leave the session usable."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await ws.send(json.dumps({"version": "1", "type": "command"}))
        error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert error["type"] == "error"
        assert error["message"] == "Invalid command message"

        await _send_command(ws, "echo valid-after-error")
        result = await _receive_until_type(ws, "exit")
        assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_ws_oversized_message_closed(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Application messages larger than 16 KiB close with code 1009."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        payload = {
            "version": "1",
            "type": "command",
            "command": "x" * 16_385,
        }
        await ws.send(json.dumps(payload))
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            await ws.recv()
        assert _close_code(exc_info.value) == 1009


@pytest.mark.asyncio
async def test_ws_second_command_rejected(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Sending a second command while one is running returns error."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
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


# ---------------------------------------------------------------------------
# C.3 Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_signal_sigint_ack(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Sending SIGINT acknowledges the signal and completes the process."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await _send_command(ws, "exec sleep 30")
        await asyncio.sleep(0.2)
        await _send_signal(ws, "SIGINT")
        msg = await _receive_until_type(ws, "signal_ack")
        assert msg.get("signal") == "SIGINT"
        result = await _receive_until_type(ws, "exit")
        assert "exit_code" in result


@pytest.mark.asyncio
async def test_ws_forbidden_signal_does_not_disconnect(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """A forbidden signal is rejected while the connection remains usable."""
    node = e2e_resources.create_ssh_node()
    url = _ws_url(service_ports, node["id"])
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        await _send_signal(ws, "SIGKILL")
        error = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert error["type"] == "error"
        assert error["message"] == "Signal rejected"

        await _send_command(ws, "echo alive-after-signal")
        result = await _receive_until_type(ws, "exit")
        assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_ws_disconnect_terminates_remote_process(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Client disconnect cancels the command and terminates its SSH process."""
    node = e2e_resources.create_ssh_node()
    pid_file = f"/tmp/ws-e2e-{uuid4().hex}.pid"
    try:
        url = _ws_url(service_ports, node["id"])
        async with websockets.connect(
            url, additional_headers={"x-api-key": "e2e-master-key-12345"}
        ) as ws:
            await _send_command(
                ws,
                (
                    "trap 'kill $child 2>/dev/null; wait $child; exit 143' TERM; "
                    f"sleep 30 & child=$!; echo $child > {pid_file}; wait $child"
                ),
            )
            await asyncio.sleep(0.5)

        deadline = asyncio.get_running_loop().time() + 10
        while True:
            response = e2e_client.post(
                f"/api/v1/nodes/{node['id']}/execute",
                json={
                    "command": (
                        f"pid=$(cat {pid_file}) && "
                        f"{{ ! kill -0 $pid 2>/dev/null || "
                        f"[ \"$(awk '{{print $3}}' /proc/$pid/stat "
                        f'2>/dev/null)" = Z ]; }}'
                    )
                },
            )
            if response.status_code == 200 and response.json()["exit_code"] == 0:
                break
            if asyncio.get_running_loop().time() >= deadline:
                process_state = e2e_client.post(
                    f"/api/v1/nodes/{node['id']}/execute",
                    json={
                        "command": (
                            f"pid=$(cat {pid_file}); "
                            f"sed -n '1,8p' /proc/$pid/status 2>/dev/null"
                        )
                    },
                )
                pytest.fail(
                    "Remote process survived WebSocket disconnect: "
                    f"{response.text}; state={process_state.text}"
                )
            await asyncio.sleep(0.2)
    finally:
        e2e_client.post(
            f"/api/v1/nodes/{node['id']}/execute",
            json={"command": f"rm -f {pid_file}"},
        )


@pytest.mark.asyncio
async def test_ws_unknown_node_closed(
    service_ports: ServicePorts, e2e_client: httpx.Client
) -> None:
    """Connecting to a non-existent node closes with code 4004."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    url = _ws_url(service_ports, fake_id)
    async with websockets.connect(
        url, additional_headers={"x-api-key": "e2e-master-key-12345"}
    ) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        msg = json.loads(raw)
        assert msg.get("type") == "error"
        # Connection should close after error
        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            await ws.recv()
        assert _close_code(exc_info.value) == 4004


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
        url = _ws_url(service_ports, node["id"])
        async with websockets.connect(
            url, additional_headers={"x-api-key": "e2e-master-key-12345"}
        ) as ws:
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


@pytest.mark.asyncio
async def test_ws_multiple_connections(
    service_ports: ServicePorts,
    e2e_client: httpx.Client,
    e2e_resources: UniqueResourceFactory,
) -> None:
    """Multiple simultaneous WebSocket connections to different nodes work."""
    node_a = e2e_resources.create_ssh_node()
    node_b = e2e_resources.create_ssh_node()

    async def run_command(node_id: str, marker: str) -> str:
        url = _ws_url(service_ports, node_id)
        async with websockets.connect(
            url, additional_headers={"x-api-key": "e2e-master-key-12345"}
        ) as ws:
            await _send_command(ws, f"echo {marker}")
            msg = await _receive_until_type(ws, "stdout", timeout=10)
            return msg.get("data", "")

    results = await asyncio.gather(
        run_command(node_a["id"], "node-a"),
        run_command(node_b["id"], "node-b"),
    )
    assert "node-a" in results[0]
    assert "node-b" in results[1]
