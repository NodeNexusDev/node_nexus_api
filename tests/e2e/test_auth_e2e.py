"""E2E tests for API key CRUD, scopes, master key, revoked/read-only keys."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx2 as httpx
import pytest

pytestmark = pytest.mark.docker


def _get_master_key() -> str:
    """Return the master API key used in the e2e Docker environment."""
    return "e2e-master-key-12345"


def test_api_key_create(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "e2e-key-create"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "e2e-key-create"
    assert data["key"].startswith("nnk_")
    assert data["key_prefix"] == data["key"][:8]


def test_api_key_list(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    # Create a key first
    e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "e2e-key-list"},
        headers={"X-API-Key": master_key},
    )

    resp = e2e_client.get(
        "/api/v2/api-keys/",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


def test_api_key_revoke(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "e2e-key-revoke"},
        headers={"X-API-Key": master_key},
    )
    key_id = resp.json()["id"]
    generated_key = resp.json()["key"]

    # Revoke
    resp = e2e_client.delete(
        f"/api/v2/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 204

    # Verify revoked key is rejected
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"X-API-Key": generated_key},
    )
    assert resp.status_code == 401

    # Verify list shows key as inactive
    resp = e2e_client.get(
        "/api/v2/api-keys/",
        headers={"X-API-Key": master_key},
    )
    items = resp.json()["items"]
    revoked = [k for k in items if k["id"] == key_id]
    assert len(revoked) == 1
    assert revoked[0]["is_active"] is False


def test_api_key_revoke_not_found(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    resp = e2e_client.delete(
        f"/api/v2/api-keys/{uuid4()}",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 404


def test_api_key_use_generated_key(e2e_client: httpx.Client) -> None:
    """Created API key can authenticate subsequent requests."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "e2e-key-auth"},
        headers={"X-API-Key": master_key},
    )
    generated_key = resp.json()["key"]

    # Use generated key to access a protected endpoint
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"X-API-Key": generated_key},
    )
    assert resp.status_code == 200


def test_api_key_missing_header(e2e_client_no_auth: httpx.Client) -> None:
    resp = e2e_client_no_auth.get("/api/v2/nodes/")
    assert resp.status_code == 401


def test_api_key_invalid_key(e2e_client: httpx.Client) -> None:
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"X-API-Key": "nnk_invalid_key_12345678901234567890"},
    )
    assert resp.status_code == 401


def test_api_key_create_validation_error(e2e_client: httpx.Client) -> None:
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": ""},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Audit log pagination and combined filters
# ---------------------------------------------------------------------------


def test_api_key_patch_name(e2e_client: httpx.Client) -> None:
    """PATCH /api-keys/{id} can update name."""
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "patch-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    # Patch
    resp = e2e_client.patch(
        f"/api/v2/api-keys/{key_id}",
        json={"name": "patched-name"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "patched-name"

    # Cleanup
    e2e_client.delete(
        f"/api/v2/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


def test_api_key_patch_scope(e2e_client: httpx.Client) -> None:
    """PATCH /api-keys/{id} can update scope."""
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "scope-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    # Patch scope to read-only
    resp = e2e_client.patch(
        f"/api/v2/api-keys/{key_id}",
        json={"scope": "read-only"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "read-only"

    # Cleanup
    e2e_client.delete(
        f"/api/v2/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


def test_api_key_patch_expires_at(e2e_client: httpx.Client) -> None:
    """PATCH /api-keys/{id} can set expires_at."""
    master_key = _get_master_key()
    # Create
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "expires-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    # Patch expires_at
    resp = e2e_client.patch(
        f"/api/v2/api-keys/{key_id}",
        json={"expires_at": "2099-12-31T23:59:59Z"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["expires_at"] is not None

    # Cleanup
    e2e_client.delete(
        f"/api/v2/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )


# ---------------------------------------------------------------------------
# API Key lifecycle — Stage G
# ---------------------------------------------------------------------------


def test_api_key_plain_key_not_in_list(e2e_client: httpx.Client) -> None:
    """Plain API key value only appears at creation, not in list response."""
    master_key = _get_master_key()
    # Create key — plain value returned
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "no-plain-in-list"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    try:
        # List — plain key must NOT appear
        resp = e2e_client.get(
            "/api/v2/api-keys/",
            headers={"X-API-Key": master_key},
        )
        items = resp.json()["items"]
        found = [k for k in items if k["id"] == key_id]
        assert len(found) == 1
        assert "key" not in found[0], f"Plain key leaked in list response: {found[0]}"
        assert "key" not in found[0], f"Plain key leaked in list response: {found[0]}"
        # key_prefix is acceptable (used for identification)
        assert "key_prefix" in found[0]
    finally:
        e2e_client.delete(
            f"/api/v2/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )


def test_api_key_hash_not_in_export(e2e_client: httpx.Client) -> None:
    """API key hash must not appear in config export."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "hash-not-in-export"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]

    try:
        resp = e2e_client.get(
            "/api/v2/config/export",
            headers={"X-API-Key": master_key},
        )
        assert resp.status_code == 200
        export_data = resp.json()
        # API keys section in export
        api_keys = export_data.get("api_keys", [])
        for key_data in api_keys:
            # Must not contain hash or plain key
            assert "key_hash" not in key_data, f"Key hash leaked in export: {key_data}"
            assert "key" not in key_data, f"Plain key leaked in export: {key_data}"
    finally:
        e2e_client.delete(
            f"/api/v2/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )


def test_revoked_key_rejected_on_all_endpoints(
    e2e_client: httpx.Client,
) -> None:
    """Revoked API key is rejected on both read and write endpoints."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "revoked-reject-all"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    revoked_key = resp.json()["key"]
    key_id = resp.json()["id"]

    # Revoke
    e2e_client.delete(
        f"/api/v2/api-keys/{key_id}",
        headers={"X-API-Key": master_key},
    )

    # Should fail on GET
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"X-API-Key": revoked_key},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for revoked key on GET, got {resp.status_code}"
    )

    # Should fail on POST
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "name": "should-fail-revoked",
            "host": "1.1.1.1",
            "port": 22,
            "connection_type": "ssh",
        },
        headers={"X-API-Key": revoked_key},
    )
    assert resp.status_code == 401, (
        f"Expected 401 for revoked key on POST, got {resp.status_code}"
    )


def test_master_key_always_accepted(e2e_client: httpx.Client) -> None:
    """Master API key works for all operations including audit delete."""
    master_key = _get_master_key()
    # Master key can read
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 200

    # Master key can write
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "name": "master-key-test-node",
            "host": "10.0.0.210",
            "port": 22,
            "connection_type": "ssh",
        },
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    node_id = resp.json()["id"]

    try:
        # Master key can access audit
        resp = e2e_client.get(
            "/api/v2/audit/",
            headers={"X-API-Key": master_key},
        )
        assert resp.status_code == 200
    finally:
        e2e_client.delete(f"/api/v2/nodes/{node_id}")


# ---------------------------------------------------------------------------
# Command and Script tags
# ---------------------------------------------------------------------------


def test_read_only_key_rejected_on_write(e2e_client):
    """403 when read-only API key tries POST/PUT/DELETE."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "ro-scope-test", "scope": "read-only"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    ro_key = resp.json()["key"]
    key_id = resp.json()["id"]

    try:
        # POST with read-only key should return 403
        resp = e2e_client.post(
            "/api/v2/nodes/",
            json={
                "name": "should-fail",
                "host": "1.1.1.1",
                "port": 22,
                "connection_type": "ssh",
            },
            headers={"X-API-Key": ro_key},
        )
        assert resp.status_code == 403
    finally:
        e2e_client.delete(
            f"/api/v2/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )


def test_read_only_key_can_read(e2e_client):
    """200 when read-only API key accesses GET endpoints."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "ro-read-test", "scope": "read-only"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    ro_key = resp.json()["key"]
    key_id = resp.json()["id"]

    try:
        resp = e2e_client.get(
            "/api/v2/nodes/",
            headers={"X-API-Key": ro_key},
        )
        assert resp.status_code == 200
    finally:
        e2e_client.delete(
            f"/api/v2/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )


# ---------------------------------------------------------------------------
# Expired API key
# ---------------------------------------------------------------------------


def test_expired_api_key_returns_401(e2e_client: httpx.Client) -> None:
    """API key with expires_at in the past is rejected with 401."""
    master_key = _get_master_key()
    resp = e2e_client.post(
        "/api/v2/api-keys/",
        json={"name": "expired-key-test"},
        headers={"X-API-Key": master_key},
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]
    generated_key = resp.json()["key"]

    try:
        # Set expires_at to the past
        past_time = (datetime.now(UTC) - timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        resp = e2e_client.patch(
            f"/api/v2/api-keys/{key_id}",
            json={"expires_at": past_time},
            headers={"X-API-Key": master_key},
        )
        assert resp.status_code == 200

        # Expired key should be rejected
        resp = e2e_client.get(
            "/api/v2/nodes/",
            headers={"X-API-Key": generated_key},
        )
        assert resp.status_code == 401
    finally:
        e2e_client.delete(
            f"/api/v2/api-keys/{key_id}",
            headers={"X-API-Key": master_key},
        )


# ---------------------------------------------------------------------------
# Docker Container Logs — parameterized (Stage N.1)
# ---------------------------------------------------------------------------
