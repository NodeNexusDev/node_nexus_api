"""E2E tests for HTTP transport-level validation.

Covers: Content-Type (415), Accept header, HTTP Method (405),
request body size limits, and deep nesting protection.

These tests verify that the API correctly enforces HTTP-level
constraints and does not crash (500) on malformed input.
"""

import json

import httpx2 as httpx
import pytest

from tests.e2e.helpers.assertions import assert_http_error

pytestmark = [pytest.mark.docker, pytest.mark.e2e_smoke]

# ---------------------------------------------------------------------------
# Content-Type validation
# ---------------------------------------------------------------------------


def test_content_type_missing_on_post(e2e_client: httpx.Client) -> None:
    """POST without Content-Type header: body is not parsed as JSON.

    FastAPI with strict_content_type=True receives the body but
    does not parse it as JSON without the header. Pydantic sees
    a raw string, fails validation → 422.
    """
    payload = (
        '{"name": "test-ct", "host": "10.0.0.99", "port": 22, "connection_type": "ssh"}'
    )
    # Use a fresh client without default headers to avoid
    # httpx auto-setting Content-Type from json= parameter.
    resp = httpx.Client().post(
        f"{e2e_client.base_url}/api/v2/nodes/",
        content=payload,
        headers={"X-API-Key": "e2e-master-key-12345"},
    )
    assert_http_error(resp, 422)


def test_content_type_text_plain(e2e_client: httpx.Client) -> None:
    """POST with text/plain Content-Type should be rejected (422).

    FastAPI with strict_content_type=True does not parse body as JSON
    when Content-Type is not application/json, leading to a Pydantic
    validation error (422), not 415.
    """
    resp = e2e_client.post(
        "/api/v2/nodes/",
        content="not-json",
        headers={"Content-Type": "text/plain"},
    )
    # FastAPI returns 422 when body can't be parsed as the expected model
    assert_http_error(resp, 422)


def test_content_type_json_with_charset(e2e_client: httpx.Client) -> None:
    """POST with application/json; charset=utf-8 should be accepted."""
    payload = {
        "name": "test-charset",
        "host": "10.0.0.100",
        "port": 22,
        "connection_type": "ssh",
    }
    resp = e2e_client.post(
        "/api/v2/nodes/",
        content=json.dumps({"items": [payload]}),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    assert resp.status_code in (200, 201, 207), (
        f"Expected 201, got {resp.status_code}: {resp.text}"
    )
    # Cleanup
    data = resp.json()
    if "results" in data:
        node_id = data["results"][0].get("node_id") or data["results"][0].get("id")
    else:
        node_id = data.get("id")
    e2e_client.delete(f"/api/v2/nodes/{node_id}")


def test_content_type_multipart_rejected(e2e_client: httpx.Client) -> None:
    """POST with multipart/form-data should be rejected (422).

    FastAPI with strict_content_type=True does not parse body as JSON
    when Content-Type is multipart/form-data, resulting in 422.
    """
    boundary = "----testboundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="name"\r\n\r\n'
        "test\r\n"
        f"--{boundary}--\r\n"
    )
    resp = e2e_client.post(
        "/api/v2/nodes/",
        content=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert_http_error(resp, 422)


# ---------------------------------------------------------------------------
# Accept header
# ---------------------------------------------------------------------------


def test_accept_json_returns_json(e2e_client: httpx.Client) -> None:
    """GET with Accept: application/json should return JSON."""
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"Accept": "application/json"},
    )
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")


def test_accept_wildcard_returns_json(e2e_client: httpx.Client) -> None:
    """GET with Accept: */* should return JSON."""
    resp = e2e_client.get(
        "/api/v2/nodes/",
        headers={"Accept": "*/*"},
    )
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# HTTP Method validation (405)
# ---------------------------------------------------------------------------


def test_method_not_allowed_put_collection(e2e_client: httpx.Client) -> None:
    """PUT on collection endpoint (no resource id) should return 405."""
    resp = e2e_client.put("/api/v2/nodes/", json={})
    assert_http_error(resp, 405)


def test_method_not_allowed_post_resource(e2e_client: httpx.Client) -> None:
    """POST on resource endpoint (with id) should return 405."""
    # Create a node first to get a valid id
    node = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "test-405-resource",
                    "host": "10.0.0.101",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert node.status_code in (200, 201, 207)
    data = node.json()
    node_id = (
        data["results"][0].get("node_id") or data["results"][0].get("id")
        if "results" in data
        else data.get("id")
    )

    try:
        resp = e2e_client.post(f"/api/v2/nodes/{node_id}", json={})
        assert resp.status_code == 405, (
            f"Expected 405, got {resp.status_code}: {resp.text}"
        )
    finally:
        e2e_client.delete(f"/api/v2/nodes/{node_id}")


def test_method_not_allowed_delete_collection(e2e_client: httpx.Client) -> None:
    """DELETE on collection endpoint should return 405."""
    resp = e2e_client.delete("/api/v2/nodes/")
    assert_http_error(resp, 405)


# ---------------------------------------------------------------------------
# Request body size / boundary values
# ---------------------------------------------------------------------------


def test_oversized_string_field_rejected(e2e_client: httpx.Client) -> None:
    """POST with a very long name field should return 422."""
    resp = e2e_client.post(
        "/api/v2/nodes/",
        json={
            "items": [
                {
                    "name": "A" * 10_000,
                    "host": "10.0.0.102",
                    "port": 22,
                    "connection_type": "ssh",
                }
            ]
        },
    )
    assert_http_error(resp, 422)
    # Detail should mention length or string constraint
    body = resp.json()
    detail = body.get("detail", [])
    if isinstance(detail, list):
        messages = " ".join(d.get("msg", "") for d in detail)
    else:
        messages = str(detail)
    assert any(
        keyword in messages.lower()
        for keyword in ("string", "length", "max", "too long", "ensure")
    ), f"Expected length constraint violation, got: {messages}"


def test_deeply_nested_json_not_500(e2e_client: httpx.Client) -> None:
    """POST with deeply nested JSON should return 4xx, not 500."""
    # Build a deeply nested dict: {"a": {"a": {"a": ...}}}
    nested: dict[str, object] = {}
    current = nested
    for _ in range(100):
        child: dict[str, object] = {}
        current["a"] = child
        current = child
    current["name"] = "deep"
    current["host"] = "10.0.0.103"
    current["port"] = 22
    current["connection_type"] = "ssh"

    resp = e2e_client.post("/api/v2/nodes/", json={"items": [nested]})
    # Must NOT be 500 — should be 4xx validation or 200 (if fields found)
    assert resp.status_code < 500, (
        f"Got 5xx ({resp.status_code}) on deeply nested JSON. Body: {resp.text[:500]}"
    )
