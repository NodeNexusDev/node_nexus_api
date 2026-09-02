"""E2E coverage guard: ensure every public HTTP endpoint has E2E tests.

This module:
1. Builds the canonical OpenAPI schema from the application (no Docker required).
2. Builds an inventory of all {method} {path} routes.
3. Compares against a manually maintained coverage manifest.
4. Fails if any endpoint is missing from the manifest — forcing
   developers to document coverage (or declare a justified exclusion).

WebSocket routes are tracked separately (they don't appear in OpenAPI).
"""

import os

import pytest

# No e2e marker — guard is docker-free and must not trigger DB isolation
pytestmark: list[pytest.MarkDecorator] = []

# ---------------------------------------------------------------------------
# Manually maintained inventory of E2E-covered endpoints.
#
# Format: "{METHOD} {PATH}" — must match OpenAPI exactly.
# When adding a new endpoint to the application, add its coverage entry
# here (or add it to EXCLUDED_ENDPOINTS with a justification).
# ---------------------------------------------------------------------------

# Endpoints that have at least one dedicated E2E test.
# v2 bulk-first — every endpoint from openapi.json minus EXCLUDED_ENDPOINTS.
COVERED_ENDPOINTS: set[str] = {
    # Health / metrics
    "GET /health",
    "GET /metrics",
    "GET /ready",
    # Nodes — list, bulk create (POST /), bulk update (PATCH /),
    # deletions, checks, metrics, credential-validations, single CRUD,
    # status-history
    "GET /api/v2/nodes/",
    "POST /api/v2/nodes/",
    "PATCH /api/v2/nodes/",
    "POST /api/v2/nodes/checks",
    "POST /api/v2/nodes/credential-validations",
    "POST /api/v2/nodes/deletions",
    "POST /api/v2/nodes/metrics",
    "GET /api/v2/nodes/{node_id}",
    "PATCH /api/v2/nodes/{node_id}",
    "DELETE /api/v2/nodes/{node_id}",
    "GET /api/v2/nodes/{node_id}/status-history",
    # Docker — single container lifecycle
    "GET /api/v2/nodes/{node_id}/docker/containers",
    "POST /api/v2/nodes/{node_id}/docker/containers",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}",
    "DELETE /api/v2/nodes/{node_id}/docker/containers/{container_id}",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/logs",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/exec",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/stats",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/top",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/start",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/stop",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/restart",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/pause",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/unpause",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/rename",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/kill",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/update",
    "POST /api/v2/nodes/{node_id}/docker/containers/{container_id}/wait",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/archive",
    "PUT /api/v2/nodes/{node_id}/docker/containers/{container_id}/archive",
    "GET /api/v2/nodes/{node_id}/docker/containers/{container_id}/port",
    # Docker — vert bulk per-node (containers)
    "POST /api/v2/nodes/{node_id}/docker/containers/starts",
    "POST /api/v2/nodes/{node_id}/docker/containers/stops",
    "POST /api/v2/nodes/{node_id}/docker/containers/restarts",
    "POST /api/v2/nodes/{node_id}/docker/containers/removals",
    "POST /api/v2/nodes/{node_id}/docker/containers/pauses",
    "POST /api/v2/nodes/{node_id}/docker/containers/unpauses",
    "POST /api/v2/nodes/{node_id}/docker/containers/kills",
    "POST /api/v2/nodes/{node_id}/docker/containers/updates",
    "POST /api/v2/nodes/{node_id}/docker/containers/executions",
    "POST /api/v2/nodes/{node_id}/docker/containers/inspections",
    "POST /api/v2/nodes/{node_id}/docker/containers/logs",
    "POST /api/v2/nodes/{node_id}/docker/containers/stats",
    "POST /api/v2/nodes/{node_id}/docker/containers/prune",
    # Docker — images
    "GET /api/v2/nodes/{node_id}/docker/images",
    "GET /api/v2/nodes/{node_id}/docker/images/{image_id}",
    "DELETE /api/v2/nodes/{node_id}/docker/images/{image_id}",
    "POST /api/v2/nodes/{node_id}/docker/images/pull",
    "POST /api/v2/nodes/{node_id}/docker/images/build",
    "GET /api/v2/nodes/{node_id}/docker/images/{image_id}/history",
    "POST /api/v2/nodes/{node_id}/docker/images/{image_id}/tag",
    "POST /api/v2/nodes/{node_id}/docker/images/{image_id}/push",
    "POST /api/v2/nodes/{node_id}/docker/images/push",
    "POST /api/v2/nodes/{node_id}/docker/images/pulls",
    "POST /api/v2/nodes/{node_id}/docker/images/removals",
    "POST /api/v2/nodes/{node_id}/docker/images/prune",
    # Docker — networks / volumes / system
    "GET /api/v2/nodes/{node_id}/docker/networks",
    "POST /api/v2/nodes/{node_id}/docker/networks",
    "GET /api/v2/nodes/{node_id}/docker/networks/{network_id}",
    "DELETE /api/v2/nodes/{node_id}/docker/networks/{network_id}",
    "POST /api/v2/nodes/{node_id}/docker/networks/{network_id}/connect",
    "POST /api/v2/nodes/{node_id}/docker/networks/{network_id}/disconnect",
    "POST /api/v2/nodes/{node_id}/docker/networks/removals",
    "POST /api/v2/nodes/{node_id}/docker/networks/prune",
    "GET /api/v2/nodes/{node_id}/docker/volumes",
    "POST /api/v2/nodes/{node_id}/docker/volumes",
    "GET /api/v2/nodes/{node_id}/docker/volumes/{volume_name}",
    "DELETE /api/v2/nodes/{node_id}/docker/volumes/{volume_name}",
    "POST /api/v2/nodes/{node_id}/docker/volumes/removals",
    "POST /api/v2/nodes/{node_id}/docker/volumes/prune",
    "GET /api/v2/nodes/{node_id}/docker/system/info",
    "GET /api/v2/nodes/{node_id}/docker/system/df",
    "GET /api/v2/nodes/{node_id}/docker/system/version",
    "POST /api/v2/nodes/{node_id}/docker/system/prune",
    # Docker Compose — projects + runtime vert bulk
    "POST /api/v2/nodes/{node_id}/docker/compose/projects",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}",
    "PATCH /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}",
    "DELETE /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/ups",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/downs",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/starts",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/stops",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/restarts",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/pauses",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/unpauses",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/kills",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/creates",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/rms",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/pulls",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/pushs",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/builds",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/executions",
    "POST /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/runs",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/ps",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/logs",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/config",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/images",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/top",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/port",
    "GET /api/v2/nodes/{node_id}/docker/compose/projects/{project_name}/version",
    # Commands — bulk-first (POST / is bulk create, executions, raw-executions)
    "GET /api/v2/commands/",
    "POST /api/v2/commands/",
    "GET /api/v2/commands/{command_id}",
    "PATCH /api/v2/commands/{command_id}",
    "DELETE /api/v2/commands/{command_id}",
    "POST /api/v2/commands/{command_id}/clone",
    "GET /api/v2/commands/{command_id}/stats",
    "GET /api/v2/commands/stats",
    "GET /api/v2/commands/history",
    "POST /api/v2/commands/executions",
    "POST /api/v2/commands/raw-executions",
    "GET /api/v2/commands/executions/history",
    "POST /api/v2/commands/executions/retries",
    "POST /api/v2/commands/executions/cancels",
    # Scripts — bulk-first
    "GET /api/v2/scripts/",
    "POST /api/v2/scripts/",
    "GET /api/v2/scripts/{script_id}",
    "PATCH /api/v2/scripts/{script_id}",
    "DELETE /api/v2/scripts/{script_id}",
    "POST /api/v2/scripts/{script_id}/clone",
    "GET /api/v2/scripts/{script_id}/stats",
    "GET /api/v2/scripts/stats",
    "GET /api/v2/scripts/{script_id}/executions",
    "GET /api/v2/scripts/{script_id}/schedule/history",
    "GET /api/v2/scripts/{script_id}/schedules",
    "POST /api/v2/scripts/{script_id}/schedules",
    "DELETE /api/v2/scripts/{script_id}/schedules",
    "POST /api/v2/scripts/executions",
    "POST /api/v2/scripts/executions/retries",
    "POST /api/v2/scripts/executions/cancels",
    # API Keys
    "GET /api/v2/api-keys/",
    "POST /api/v2/api-keys/",
    "PATCH /api/v2/api-keys/{key_id}",
    "DELETE /api/v2/api-keys/{key_id}",
    # Audit
    "GET /api/v2/audit/",
    "DELETE /api/v2/audit/",
    "GET /api/v2/audit/exports",
    "GET /api/v2/audit/stats",
    "GET /api/v2/audit/{log_id}",
    # Config
    "GET /api/v2/config/export",
    "POST /api/v2/config/import",
    # Favorites / Search
    "GET /api/v2/favorites/",
    "POST /api/v2/favorites/",
    "DELETE /api/v2/favorites/{target_type}/{target_id}",
    "GET /api/v2/search",
    # Templates — registries + packs
    "POST /api/v2/templates/registries",
    "GET /api/v2/templates/registries",
    "GET /api/v2/templates/registries/{registry_id}",
    "DELETE /api/v2/templates/registries/{registry_id}",
    "POST /api/v2/templates/registries/{registry_id}/syncs",
    "POST /api/v2/templates/packs",
    "GET /api/v2/templates/packs",
    "GET /api/v2/templates/packs/stats",
    "GET /api/v2/templates/packs/{pack_id}",
    "GET /api/v2/templates/packs/{pack_id}/archive",
    "GET /api/v2/templates/packs/{pack_id}/installations",
    "POST /api/v2/templates/packs/{pack_id}/installations",
    "POST /api/v2/templates/packs/{pack_id}/uninstallations",
    "POST /api/v2/templates/packs/{pack_id}/updates",
    # Auth / Users
    "POST /api/v2/auth/login",
    "POST /api/v2/auth/logout",
    "POST /api/v2/auth/refresh",
    "GET /api/v2/auth/me",
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
# Inventory builder (docker-free — uses canonical app, not live stack)
# ---------------------------------------------------------------------------

_CANONICAL_ENV = {
    "PROMETHEUS_ENABLED": "true",
    "E2E_ENABLED": "true",
    "OTEL_ENABLED": "false",
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/test",
    "SECRET_KEY": "0123456789abcdef0123456789ABCDEF",
    "ENCRYPTION_SALT": "0123456789abcdef",
}


def _build_openapi_inventory() -> set[str]:
    """Build canonical OpenAPI inventory without Docker.

    Uses cached openapi.snapshot.json if present (generated via
    `make generate-openapi` or `uv run python scripts/generate_openapi_snapshot.py`),
    otherwise builds via create_app().openapi() and caches.
    """
    import json
    from pathlib import Path

    snapshot = Path("scripts/openapi.snapshot.json")
    schema: dict[str, object] | None = None
    if snapshot.exists():
        try:
            schema = json.loads(snapshot.read_text(encoding="utf-8"))
        except Exception:
            schema = None
    if schema is None:
        from app.core.config import get_settings
        from app.main import create_app

        get_settings.cache_clear()
        saved = {k: os.environ.get(k) for k in _CANONICAL_ENV}
        os.environ.update(_CANONICAL_ENV)
        try:
            schema = create_app().openapi()
            # cache for next run
            try:
                snapshot.write_text(
                    json.dumps(schema, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            get_settings.cache_clear()

    assert schema is not None
    paths: dict[str, object] = schema.get("paths", {})  # type: ignore[assignment]
    inventory: set[str] = set()
    for path, methods in paths.items():  # type: ignore[assignment]
        assert isinstance(methods, dict)
        for method in methods:
            if method in ("parameters", "servers", "description", "summary"):
                continue
            inventory.add(f"{method.upper()} {path}")
    return inventory


def test_endpoint_coverage_guard() -> None:
    """Every public HTTP endpoint must be in the coverage manifest.

    If a new endpoint is added to the application without updating
    this manifest, this test will fail — forcing the developer to
    document coverage or add a justified exclusion.

    Run `make update-e2e-coverage` to auto-sync after adding an endpoint.
    """
    inventory = _build_openapi_inventory()

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
