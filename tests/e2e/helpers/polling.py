"""Polling helpers with monotonic deadline for E2E tests."""

import time
from collections.abc import Callable

import httpx2 as httpx

from tests.types import UnvalidatedJsonObject


def wait_for_condition(
    condition: Callable[[], bool],
    *,
    timeout: float = 30.0,
    pause: float = 0.5,
    description: str = "condition",
) -> None:
    """Poll a callable until it returns True or timeout expires.

    Uses monotonic clock — immune to system time changes.
    """
    started_at = time.monotonic()
    deadline = started_at + timeout
    while True:
        if condition():
            return
        if time.monotonic() >= deadline:
            elapsed = time.monotonic() - started_at
            raise AssertionError(
                f"Timed out after {elapsed:.1f}s waiting for: {description} "
                f"(budget={timeout:.1f}s)"
            )
        time.sleep(pause)


def wait_for_container_status(
    e2e_client: httpx.Client,
    node_id: str,
    container_id: str,
    expected_status: str,
    *,
    timeout: float = 30.0,
) -> None:
    """Poll GET .../containers/{cid} until container reaches expected status."""
    description = f"container {container_id} status={expected_status}"

    def _check() -> bool:
        resp = e2e_client.get(
            f"/api/v2/nodes/{node_id}/docker/containers/{container_id}"
        )
        if resp.status_code != 200:
            return False
        state = resp.json().get("State", {})
        return bool(state.get("status", "").lower() == expected_status.lower())

    wait_for_condition(_check, timeout=timeout, description=description)


def wait_for_image_present(
    e2e_client: httpx.Client,
    node_id: str,
    image: str,
    *,
    timeout: float = 60.0,
) -> None:
    """Poll GET .../docker/images until a specific image appears."""
    description = f"image {image} present"

    def _check() -> bool:
        resp = e2e_client.get(f"/api/v2/nodes/{node_id}/docker/images")
        if resp.status_code != 200:
            return False
        images = resp.json()
        for img in images:
            repo = img.get("Repository", "")
            tag = img.get("Tag", "")
            if f"{repo}:{tag}" == image or repo == image or image in str(img):
                return True
        return False

    wait_for_condition(_check, timeout=timeout, description=description)


def wait_for_audit_record(
    e2e_client: httpx.Client,
    *,
    query: str = "",
    action: str | None = None,
    minimum_total: int = 1,
    timeout: float = 10.0,
) -> UnvalidatedJsonObject:
    """Poll the eventually-consistent audit log until expected records appear.

    Returns the parsed JSON response.
    """
    started_at = time.monotonic()
    deadline = started_at + timeout
    while True:
        response = e2e_client.get(f"/api/v2/audit/{query}")
        assert response.status_code == 200
        data = response.json()
        actions = {item["action"] for item in data["items"]}
        if data["total"] >= minimum_total and (action is None or action in actions):
            return data
        if time.monotonic() >= deadline:
            elapsed = time.monotonic() - started_at
            raise AssertionError(
                f"Audit record not delivered: action={action}, query={query}, "
                f"total={data.get('total', 0)}, actions_found={actions}, "
                f"elapsed={elapsed:.1f}s, budget={timeout:.1f}s"
            )
        time.sleep(0.1)
