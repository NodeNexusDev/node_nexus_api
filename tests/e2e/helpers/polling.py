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

    Supports cursor pagination (``CursorPage`` with ``items``, ``next_cursor``,
    ``has_more``, ``limit``) and falls back to legacy ``total``/``page``/``size``.
    Collects all pages via ``cursor``/``limit`` and checks ``action`` locally.

    Returns the parsed JSON response (synthesized with ``total``/``page``/``size``
    for backward compatibility).
    """
    started_at = time.monotonic()
    deadline = started_at + timeout
    while True:
        # Collect all pages via cursor pagination
        all_items: list[UnvalidatedJsonObject] = []
        cursor: str | None = None
        has_more = True
        next_cursor: str | None = None
        limit = 100
        legacy_total: int | None = None
        base_path = f"/api/v2/audit/{query}" if query else "/api/v2/audit/"
        # Ensure path ends correctly – ``query`` may already start with ``?``
        # httpx will merge ``params`` correctly even when URL has a query string.
        while has_more:
            params: dict[str, str | int] = {"limit": limit}
            if cursor is not None:
                params["cursor"] = cursor
            response = e2e_client.get(base_path, params=params)
            assert response.status_code == 200
            data = response.json()
            if "has_more" not in data and "next_cursor" not in data:
                items = data.get("items", [])
                if isinstance(items, list):
                    all_items.extend(items)  # type: ignore[arg-type]
                legacy_total = int(data.get("total", len(all_items)))
                has_more = False
                next_cursor = None
                break
            items = data.get("items", [])
            if isinstance(items, list):
                all_items.extend(items)  # type: ignore[arg-type]
            next_cursor = data.get("next_cursor")
            has_more = bool(data.get("has_more", False))
            limit = int(data.get("limit", limit))
            if not has_more or not next_cursor:
                has_more = False
                break
            cursor = str(next_cursor)
            if len(all_items) >= minimum_total and (
                action is None or any(i.get("action") == action for i in all_items)
            ):
                break
            if len(all_items) > 10000:
                has_more = False
                break

        effective_total = legacy_total if legacy_total is not None else len(all_items)
        actions = {item.get("action") for item in all_items if isinstance(item, dict)}
        if effective_total >= minimum_total and (action is None or action in actions):
            # Synthesize legacy fields for callers expecting ``total``/``page``/``size``
            return {
                "items": all_items,
                "total": effective_total,
                "page": 1,
                "size": len(all_items),
                "has_more": has_more,
                "next_cursor": next_cursor,
                "limit": limit,
            }
        if time.monotonic() >= deadline:
            elapsed = time.monotonic() - started_at
            raise AssertionError(
                f"Audit record not delivered: action={action}, query={query}, "
                f"total={effective_total}, actions_found={actions}, "
                f"elapsed={elapsed:.1f}s, budget={timeout:.1f}s"
            )
        time.sleep(0.1)
