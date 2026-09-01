"""E2E tests for concurrency and race conditions.

These tests use asyncio.gather with barriers/events to ensure
requests truly overlap, not execute sequentially.

Marker: e2e_resilience
"""

import asyncio
from uuid import uuid4

import httpx2 as httpx
import pytest

from tests.e2e.conftest import ServicePorts

pytestmark = [pytest.mark.docker, pytest.mark.e2e_resilience]


def _base_url(service_ports: ServicePorts) -> str:
    return f"http://{service_ports.api_host}:{service_ports.api_port}"


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": "e2e-master-key-12345"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _release_on_event(event: asyncio.Event, coro):
    """Wait for event, then execute the coroutine."""
    await event.wait()
    return await coro


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_create_same_name(
    service_ports: ServicePorts,
) -> None:
    """Two concurrent POST /nodes with same name: one succeeds, one fails."""
    base = _base_url(service_ports)
    name = f"concurrent-{uuid4().hex[:8]}"
    barrier = asyncio.Event()

    async def create() -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=base, timeout=30.0, headers=_auth_headers()
        ) as client:
            # Wait for barrier before sending
            await barrier.wait()
            return await client.post(
                "/api/v2/nodes/",
                json={
                    "items": [
                        {
                            "name": name,
                            "host": "10.0.0.1",
                            "port": 22,
                            "connection_type": "ssh",
                        }
                    ]
                },
            )

    # Start both concurrently
    task_a = asyncio.create_task(create())
    task_b = asyncio.create_task(create())
    await asyncio.sleep(0.05)
    barrier.set()  # Release both
    resp_a, resp_b = await asyncio.gather(task_a, task_b)

    # Bulk-first: one succeeds (succeeded=1), the other fails (failed=1)
    def _succeeded(resp: httpx.Response) -> bool:
        try:
            data = resp.json()
            if isinstance(data, dict) and "results" in data:
                return bool(data.get("succeeded") == 1)
            return resp.status_code == 201
        except Exception:
            return False

    succeeded = sum(1 for r in (resp_a, resp_b) if _succeeded(r))
    failed = 2 - succeeded
    assert succeeded == 1, (
        f"Expected one success, got {resp_a.status_code} {resp_a.text[:200]} "
        f"and {resp_b.status_code} {resp_b.text[:200]}"
    )
    assert failed == 1

    # Cleanup the created node
    for resp in (resp_a, resp_b):
        try:
            data = resp.json()
            if isinstance(data, dict) and "results" in data:
                first = data["results"][0]
                is_ok = data.get("succeeded") == 1 and first.get("status") == "success"
                if is_ok:
                    node_id = first.get("node_id") or first.get("id")
                    if node_id:
                        async with httpx.AsyncClient(
                            base_url=base,
                            timeout=30.0,
                            headers=_auth_headers(),
                        ) as client:
                            await client.delete(f"/api/v2/nodes/{node_id}")
            elif resp.status_code == 201:
                node_id = data.get("id")
                if node_id:
                    async with httpx.AsyncClient(
                        base_url=base, timeout=30.0, headers=_auth_headers()
                    ) as client:
                        await client.delete(f"/api/v2/nodes/{node_id}")
        except Exception:
            continue


@pytest.mark.asyncio
async def test_repeat_delete_idempotent(
    service_ports: ServicePorts,
) -> None:
    """Repeated DELETE of same resource: first 204, subsequent 404 — never 500."""
    base = _base_url(service_ports)

    async with httpx.AsyncClient(
        base_url=base, timeout=30.0, headers=_auth_headers()
    ) as client:
        # Create node
        resp = await client.post(
            "/api/v2/nodes/",
            json={
                "items": [
                    {
                        "name": f"idempotent-del-{uuid4().hex[:8]}",
                        "host": "10.0.0.1",
                        "port": 22,
                        "connection_type": "ssh",
                    }
                ]
            },
        )
        assert resp.status_code in (200, 201, 207)
        data = resp.json()
        node_id = data["results"][0]["node_id"] if "results" in data else data["id"]

        # First delete — should succeed
        resp1 = await client.delete(f"/api/v2/nodes/{node_id}")
        assert resp1.status_code == 204, f"First delete: {resp1.status_code}"

        # Second delete — should be 404
        resp2 = await client.delete(f"/api/v2/nodes/{node_id}")
        assert resp2.status_code == 404, (
            f"Second delete: expected 404, got {resp2.status_code}"
        )

        # Third delete — still 404, never 500
        resp3 = await client.delete(f"/api/v2/nodes/{node_id}")
        assert resp3.status_code == 404, (
            f"Third delete: expected 404, got {resp3.status_code}"
        )


@pytest.mark.asyncio
async def test_concurrent_patch_api_key(
    service_ports: ServicePorts,
) -> None:
    """Concurrent PATCH on same API key: final state is consistent."""
    base = _base_url(service_ports)

    async with httpx.AsyncClient(
        base_url=base, timeout=30.0, headers=_auth_headers()
    ) as client:
        # Create API key
        resp = await client.post(
            "/api/v2/api-keys/",
            json={"name": "concurrent-patch-key"},
        )
        assert resp.status_code == 201
        key_id = resp.json()["id"]

        try:
            barrier = asyncio.Event()

            async def patch_name(new_name: str) -> httpx.Response:
                async with httpx.AsyncClient(
                    base_url=base, timeout=30.0, headers=_auth_headers()
                ) as c:
                    await barrier.wait()
                    return await c.patch(
                        f"/api/v2/api-keys/{key_id}",
                        json={"name": new_name},
                    )

            task_a = asyncio.create_task(patch_name("name-a"))
            task_b = asyncio.create_task(patch_name("name-b"))
            await asyncio.sleep(0.05)
            barrier.set()
            resp_a, resp_b = await asyncio.gather(task_a, task_b)

            # Both should succeed (200)
            assert resp_a.status_code == 200
            assert resp_b.status_code == 200

            # Final name should be one of the two (consistent state)
            resp = await client.get("/api/v2/api-keys/")
            assert resp.status_code == 200
            items = resp.json()["items"]
            key_data = [k for k in items if k["id"] == key_id]
            assert len(key_data) == 1
            final_name = key_data[0]["name"]
            assert final_name in ("name-a", "name-b"), (
                f"Unexpected final name: {final_name}"
            )
        finally:
            await client.delete(f"/api/v2/api-keys/{key_id}")


@pytest.mark.asyncio
async def test_concurrent_config_imports(
    service_ports: ServicePorts,
) -> None:
    """Two concurrent config imports: neither corrupts the DB."""
    base = _base_url(service_ports)

    barrier = asyncio.Event()

    async def do_import(suffix: str) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=base, timeout=30.0, headers=_auth_headers()
        ) as client:
            await barrier.wait()
            return await client.post(
                "/api/v2/config/import",
                json={
                    "nodes": [
                        {
                            "name": f"cc-import-{suffix}",
                            "host": "10.0.0.1",
                            "port": 22,
                            "connection_type": "ssh",
                        }
                    ]
                },
            )

    task_a = asyncio.create_task(do_import("a"))
    task_b = asyncio.create_task(do_import("b"))
    await asyncio.sleep(0.05)
    barrier.set()
    resp_a, resp_b = await asyncio.gather(task_a, task_b)

    # Both should complete without 500
    assert resp_a.status_code < 500, f"Import A: {resp_a.status_code}"
    assert resp_b.status_code < 500, f"Import B: {resp_b.status_code}"

    # Cleanup
    async with httpx.AsyncClient(
        base_url=base, timeout=30.0, headers=_auth_headers()
    ) as client:
        resp = await client.get("/api/v2/nodes/?limit=100")
        for n in resp.json()["items"]:
            if n["name"].startswith("cc-import-"):
                await client.delete(f"/api/v2/nodes/{n['id']}")


@pytest.mark.asyncio
async def test_concurrent_bulk_commands(
    service_ports: ServicePorts,
) -> None:
    """Concurrent bulk command executions don't share DB sessions."""
    base = _base_url(service_ports)

    async with httpx.AsyncClient(
        base_url=base, timeout=30.0, headers=_auth_headers()
    ) as client:
        # Create two nodes
        nodes = []
        for i in range(2):
            resp = await client.post(
                "/api/v2/nodes/",
                json={
                    "items": [
                        {
                            "name": f"cc-bulk-{uuid4().hex[:8]}",
                            "host": "ssh-server",
                            "port": 2222,
                            "connection_type": "ssh",
                            "username": "testuser",
                            "password": "testpass",
                        }
                    ]
                },
            )
            assert resp.status_code in (200, 201, 207)
            data = resp.json()
            nid = data["results"][0]["node_id"] if "results" in data else data["id"]
            nodes.append({"id": nid})

        try:
            barrier = asyncio.Event()

            async def run_bulk() -> httpx.Response:
                async with httpx.AsyncClient(
                    base_url=base, timeout=30.0, headers=_auth_headers()
                ) as c:
                    await barrier.wait()
                    return await c.post(
                        "/api/v2/commands/raw-executions",
                        json={
                            "node_ids": [n["id"] for n in nodes],
                            "commands": ["echo bulk-ok"],
                        },
                    )

            task_a = asyncio.create_task(run_bulk())
            task_b = asyncio.create_task(run_bulk())
            await asyncio.sleep(0.05)
            barrier.set()
            resp_a, resp_b = await asyncio.gather(task_a, task_b)

            # Both should complete without session errors
            assert resp_a.status_code < 500, (
                f"Bulk A failed: {resp_a.status_code} {resp_a.text[:200]}"
            )
            assert resp_b.status_code < 500, (
                f"Bulk B failed: {resp_b.status_code} {resp_b.text[:200]}"
            )
        finally:
            for n in nodes:
                await client.delete(f"/api/v2/nodes/{n['id']}")
