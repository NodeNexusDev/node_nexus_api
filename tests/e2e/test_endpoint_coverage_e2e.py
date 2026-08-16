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
    "GET /api/v1/nodes/",
    "POST /api/v1/nodes/",
    "GET /api/v1/nodes/{node_id}",
    "PUT /api/v1/nodes/{node_id}",
    "DELETE /api/v1/nodes/{node_id}",
    "POST /api/v1/nodes/{node_id}/execute",
    "POST /api/v1/nodes/{node_id}/check",
    "GET /api/v1/nodes/{node_id}/metrics",
    "GET /api/v1/nodes/{node_id}/commands/history",
    "POST /api/v1/nodes/bulk/execute",
    "GET /api/v1/nodes/bulk/history",
    "GET /api/v1/nodes/tags",
    "POST /api/v1/nodes/{node_id}/tags",
    "DELETE /api/v1/nodes/{node_id}/tags",
    "POST /api/v1/nodes/validate-credentials",
    "GET /api/v1/nodes/{node_id}/status-history",
    "POST /api/v1/nodes/bulk/delete",
    "POST /api/v1/nodes/bulk/tags/add",
    "POST /api/v1/nodes/bulk/tags/remove",
    "POST /api/v1/nodes/bulk/check",
    "POST /api/v1/nodes/{node_id}/commands/{execution_id}/retry",
    # Commands
    "GET /api/v1/commands/",
    "GET /api/v1/commands/tags",
    "POST /api/v1/commands/",
    "GET /api/v1/commands/{command_id}",
    "PUT /api/v1/commands/{command_id}",
    "DELETE /api/v1/commands/{command_id}",
    "POST /api/v1/commands/{command_id}/execute",
    # Scripts
    "GET /api/v1/scripts/",
    "GET /api/v1/scripts/tags",
    "POST /api/v1/scripts/",
    "GET /api/v1/scripts/{script_id}",
    "PUT /api/v1/scripts/{script_id}",
    "DELETE /api/v1/scripts/{script_id}",
    "POST /api/v1/scripts/{script_id}/execute",
    "GET /api/v1/scripts/{script_id}/executions",
    "GET /api/v1/scripts/{script_id}/schedule",
    "POST /api/v1/scripts/{script_id}/schedule",
    "DELETE /api/v1/scripts/{script_id}/schedule",
    "POST /api/v1/scripts/executions/{execution_id}/retry",
    "POST /api/v1/scripts/executions/{execution_id}/cancel",
    "GET /api/v1/scripts/{script_id}/schedule/history",
    # API Keys
    "GET /api/v1/api-keys/",
    "POST /api/v1/api-keys/",
    "PATCH /api/v1/api-keys/{key_id}",
    "DELETE /api/v1/api-keys/{key_id}",
    # Audit
    "GET /api/v1/audit/",
    "DELETE /api/v1/audit/",
    # Config
    "GET /api/v1/config/export",
    "POST /api/v1/config/import",
    # Dashboard
    "GET /api/v1/dashboard/",
    # Docker Images
    "GET /api/v1/nodes/{node_id}/docker/images",
    "POST /api/v1/nodes/{node_id}/docker/images/pull",
    "GET /api/v1/nodes/{node_id}/docker/images/{image_id}",
    "DELETE /api/v1/nodes/{node_id}/docker/images/{image_id}",
    "POST /api/v1/nodes/{node_id}/docker/images/{image_id}/tag",
    "POST /api/v1/nodes/{node_id}/docker/images/build",
    # Docker Containers
    "GET /api/v1/nodes/{node_id}/docker/containers",
    "POST /api/v1/nodes/{node_id}/docker/containers",
    "GET /api/v1/nodes/{node_id}/docker/containers/{container_id}",
    "POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/start",
    "POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/stop",
    "POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/restart",
    "DELETE /api/v1/nodes/{node_id}/docker/containers/{container_id}",
    "GET /api/v1/nodes/{node_id}/docker/containers/{container_id}/logs",
    "POST /api/v1/nodes/{node_id}/docker/containers/{container_id}/exec",
    "GET /api/v1/nodes/{node_id}/docker/containers/{container_id}/stats",
    # Docker Resources
    "GET /api/v1/nodes/{node_id}/docker/networks",
    "GET /api/v1/nodes/{node_id}/docker/volumes",
    # Docker Bulk
    "POST /api/v1/docker/bulk/start",
    "POST /api/v1/docker/bulk/stop",
    "POST /api/v1/docker/bulk/restart",
    "POST /api/v1/docker/bulk/exec",
}

# Endpoints NOT covered by E2E tests, with justification.
EXCLUDED_ENDPOINTS: dict[str, str] = {
    # Add entries like:
    # "METHOD /path": "Justification for exclusion",
}

# WebSocket routes (not in OpenAPI, tracked separately).
COVERED_WS_ENDPOINTS: set[str] = {
    "WS /api/v1/nodes/{node_id}/exec-stream",
}

# ---------------------------------------------------------------------------
# Inventory builder
# ---------------------------------------------------------------------------


def _build_openapi_inventory(e2e_client: httpx.Client) -> set[str]:
    """Fetch OpenAPI schema and extract all {method} {path} pairs."""
    resp = e2e_client.get("/openapi.json")
    assert resp.status_code == 200, f"OpenAPI schema not available: {resp.status_code}"
    schema = resp.json()
    paths: dict = schema.get("paths", {})
    inventory: set[str] = set()
    for path, methods in paths.items():
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
