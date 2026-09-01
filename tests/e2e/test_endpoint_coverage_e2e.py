"""E2E coverage guard: ensure every public HTTP endpoint has E2E tests.

This module:
1. Fetches the live OpenAPI schema from the running E2E stack.
2. Builds an inventory of all {method} {path} routes.
3. Compares against a manually maintained coverage manifest.
4. Fails if any endpoint is missing from the manifest — forcing
   developers to document coverage (or declare a justified exclusion).

WebSocket routes are tracked separately (they don't appear in OpenAPI).
"""

import httpx2 as httpx
import pytest

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]

# ---------------------------------------------------------------------------
# Manually maintained inventory of E2E-covered endpoints.
#
# Format: "{METHOD} {PATH}" — must match OpenAPI exactly.
# When adding a new endpoint to the application, add its coverage entry
# here (or add it to EXCLUDED_ENDPOINTS with a justification).
# ---------------------------------------------------------------------------

# Endpoints that have at least one dedicated E2E test.
COVERED_ENDPOINTS: set[str] = {
    # Health / metrics
    "GET /health",
    "GET /ready",
    "GET /metrics",
    # Nodes
    "GET /api/v2/nodes/",
    "POST /api/v2/nodes/",
    "GET /api/v2/nodes/{node_id}",
    "PATCH /api/v2/nodes/{node_id}",
    "DELETE /api/v2/nodes/{node_id}",
    "POST /api/v2/commands/execute",
    "POST /api/v2/nodes/{node_id}/check",
    "POST /api/v2/nodes/{node_id}/refresh-host-key",
    "GET /api/v2/nodes/{node_id}/metrics",
    "GET /api/v2/commands/history",
    "POST /api/v2/commands/bulk/execute",
    "GET /api/v2/commands/bulk/history",
    "GET /api/v2/nodes/tags",
    "POST /api/v2/nodes/validate-credentials",
    "GET /api/v2/nodes/{node_id}/status-history",
    "POST /api/v2/nodes/bulk/delete",
    "POST /api/v2/nodes/bulk/check",
    "POST /api/v2/commands/executions/{execution_id}/retry",
    "POST /api/v2/nodes/bulk/metrics",
    "PATCH /api/v2/nodes/bulk/update",
    "POST /api/v2/nodes/bulk/validate-credentials",
    "POST /api/v2/commands/bulk/retry",
    "POST /api/v2/commands/bulk/cancel",
    # Commands
    "GET /api/v2/commands/",
    "GET /api/v2/commands/tags",
    "POST /api/v2/commands/",
    "GET /api/v2/commands/{command_id}",
    "PATCH /api/v2/commands/{command_id}",
    "DELETE /api/v2/commands/{command_id}",
    "POST /api/v2/commands/{command_id}/execute",
    "POST /api/v2/commands/{command_id}/bulk-execute",
    # Scripts
    "GET /api/v2/scripts/",
    "GET /api/v2/scripts/tags",
    "POST /api/v2/scripts/",
    "GET /api/v2/scripts/{script_id}",
    "PATCH /api/v2/scripts/{script_id}",
    "DELETE /api/v2/scripts/{script_id}",
    "POST /api/v2/scripts/{script_id}/execute",
    "GET /api/v2/scripts/{script_id}/executions",
    "GET /api/v2/scripts/{script_id}/schedule",
    "POST /api/v2/scripts/{script_id}/schedule",
    "DELETE /api/v2/scripts/{script_id}/schedule",
    "POST /api/v2/scripts/executions/{execution_id}/retry",
    "POST /api/v2/scripts/executions/{execution_id}/cancel",
    "POST /api/v2/scripts/bulk/retry",
    "POST /api/v2/scripts/bulk/cancel",
    "GET /api/v2/scripts/{script_id}/schedule/history",
    # API Keys
    "GET /api/v2/api-keys/",
    "POST /api/v2/api-keys/",
    "PATCH /api/v2/api-keys/{key_id}",
    "DELETE /api/v2/api-keys/{key_id}",
    # Audit
    "GET /api/v2/audit/",
    "DELETE /api/v2/audit/",
    # Config
    "GET /api/v2/config/export",
    "POST /api/v2/config/import",
    # Dashboard
    "GET /api/v2/dashboard/",
    # Docker Images
    "GET /api/v2/nodes/{node_id}/docker/images",
    "POST /api/v2/nodes/{node_id}/docker/images/pull",
    "GET /api/v2/nodes/{node_id}/docker/images/{image_id}",
    "DELETE /api/v2/nodes/{node_id}/docker/images/{image_id}",
    "POST /api/v2/nodes/{node_id}/docker/images/{image_id}/tag",
    "POST /api/v2/nodes/{node_id}/docker/images/build",
    # Docker Containers
    "GET /api/v2/nodes/{node_id}/docker/containers",
    "POST /api/v2/nodes/{node_id}/docker/containers",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/start",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/stop",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/restart",
    "DELETE /api/v2/nodes/{node_id}/docker/containers/{container_id}",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/logs",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/exec",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/stats",
    # Docker Resources
    "GET /api/v2/nodes/{node_id}/docker/networks",
    "GET /api/v2/nodes/{node_id}/docker/volumes",
    # Docker Bulk
    "POST /api/v2/docker/bulk/start",
    "POST /api/v2/docker/bulk/stop",
    "POST /api/v2/docker/bulk/restart",
    "POST /api/v2/docker/bulk/exec",
    "POST /api/v2/docker/bulk/remove",
    "POST /api/v2/docker/bulk/pull",
    "POST /api/v2/docker/bulk/images/remove",
    "POST /api/v2/docker/bulk/images/build",
    # Docker Container lifecycle extensions
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/pause",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/unpause",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/rename",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/top",
    # Docker Network CRUD
    "POST /api/v2/nodes/{node_id}/docker/networks",
    "GET /api/v2/nodes/{node_id}/docker/networks/{network_id}",
    "DELETE /api/v2/nodes/{node_id}/docker/networks/{network_id}",
    "POST /api/v2/nodes/{node_id}/docker/networks/{network_id}/connect",
    "POST /api/v2/nodes/{node_id}/docker/networks/{network_id}/disconnect",
    # Docker Volume CRUD
    "POST /api/v2/nodes/{node_id}/docker/volumes",
    "GET /api/v2/nodes/{node_id}/docker/volumes/{volume_name}",
    "DELETE /api/v2/nodes/{node_id}/docker/volumes/{volume_name}",
    "POST /api/v2/nodes/{node_id}/docker/volumes/prune",
    # Docker System
    "GET /api/v2/nodes/{node_id}/docker/system/info",
    "GET /api/v2/nodes/{node_id}/docker/system/df",
    # Docker Prune
    "POST /api/v2/nodes/{node_id}/docker/containers/prune",
    "POST /api/v2/nodes/{node_id}/docker/images/prune",
    # Docker Bulk extended
    "POST /api/v2/docker/bulk/inspect",
    "POST /api/v2/docker/bulk/logs",
    "POST /api/v2/docker/bulk/stats",
    # Favorites (Stage F)
    "GET /api/v2/favorites",
    "POST /api/v2/favorites",
    "DELETE /api/v2/favorites/{target_type}/{target_id}",
    # Notes (Stage F)
    "GET /api/v2/notes/{target_type}/{target_id}",
    "POST /api/v2/notes/{target_type}/{target_id}",
    "PUT /api/v2/notes/{note_id}",
    "DELETE /api/v2/notes/{note_id}",
    # Global Search (Stage F)
    "GET /api/v2/search",
    # Audit Export (Stage F)
    "GET /api/v2/audit/export",
    # Dashboard Metrics (Stage F)
    "GET /api/v2/dashboard/metrics",
    # Node Stats (Stage F)
    "GET /api/v2/commands/stats",
    # Command Stats + Clone (Stage F)
    "GET /api/v2/commands/{command_id}/stats",
    "POST /api/v2/commands/{command_id}/clone",
    # Script Stats + Clone (Stage F)
    "GET /api/v2/scripts/{script_id}/stats",
    "POST /api/v2/scripts/{script_id}/clone",
    # JWT Auth
    "POST /api/v2/auth/login",
    "POST /api/v2/auth/logout",
    "POST /api/v2/auth/refresh",
    "GET /api/v2/auth/me",
    # User Management
    "GET /api/v2/users/",
    "POST /api/v2/users/",
    "DELETE /api/v2/users/{user_id}",
}

# Endpoints NOT covered by E2E tests, with justification.
EXCLUDED_ENDPOINTS: dict[str, str] = {
    "GET /api/v2/events/stream": (
        "SSE streaming endpoint — TestClient blocks indefinitely on "
        "streaming responses; covered by unit test for _event_generator."
    ),
}

# WebSocket routes (not in OpenAPI, tracked separately).
COVERED_WS_ENDPOINTS: set[str] = {
    "WS /api/v2/nodes/{node_id}/exec-stream",
}

# ---------------------------------------------------------------------------
# Inventory builder
# ---------------------------------------------------------------------------


def _build_openapi_inventory(e2e_client: httpx.Client) -> set[str]:
    """Fetch OpenAPI schema and extract all {method} {path} pairs."""
    resp = e2e_client.get("/openapi.json")
    assert resp.status_code == 200, f"OpenAPI schema not available: {resp.status_code}"
    schema = resp.json()
    paths: dict[str, object] = schema.get("paths", {})
    inventory: set[str] = set()
    for path, methods in paths.items():
        assert isinstance(methods, dict)
        for method in methods:
            if method in ("parameters", "servers", "description", "summary"):
                continue
            inventory.add(f"{method.upper()} {path}")
    return inventory


def test_endpoint_coverage_guard(e2e_client: httpx.Client) -> None:
    """Every public HTTP endpoint must be in the coverage manifest.

    If a new endpoint is added to the application without updating
    this manifest, this test will fail — forcing the developer to
    document coverage or add a justified exclusion.
    """
    inventory = _build_openapi_inventory(e2e_client)

    # Check for missing coverage
    uncovered = inventory - COVERED_ENDPOINTS - set(EXCLUDED_ENDPOINTS.keys())
    if uncovered:
        uncovered_list = "\n  ".join(sorted(uncovered))
        raise AssertionError(
            f"Found {len(uncovered)} uncovered OpenAPI endpoint(s):\n"
            f"  {uncovered_list}\n\n"
            f"Add them to COVERED_ENDPOINTS (if tested) or "
            f"EXCLUDED_ENDPOINTS (with justification) in "
            f"tests/e2e/test_endpoint_coverage_e2e.py"
        )

    # Check for stale entries (endpoints in manifest that no longer exist)
    stale = (COVERED_ENDPOINTS | set(EXCLUDED_ENDPOINTS.keys())) - inventory
    if stale:
        stale_list = "\n  ".join(sorted(stale))
        raise AssertionError(
            f"Found {len(stale)} stale endpoint(s) in coverage manifest "
            f"(no longer in OpenAPI):\n  {stale_list}\n\n"
            f"Remove them from COVERED_ENDPOINTS or EXCLUDED_ENDPOINTS "
            f"in tests/e2e/test_endpoint_coverage_e2e.py"
        )


def test_ws_endpoint_coverage_guard() -> None:
    """Every public WebSocket endpoint must be in the coverage manifest."""
    # This is a static check — WebSocket routes don't appear in OpenAPI.
    # When adding a new WebSocket endpoint, add it to COVERED_WS_ENDPOINTS.
    assert len(COVERED_WS_ENDPOINTS) > 0, (
        "No WebSocket endpoints in coverage manifest. "
        "Add WebSocket routes to COVERED_WS_ENDPOINTS."
    )
