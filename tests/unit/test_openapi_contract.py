"""OpenAPI contract quality checks."""

import hashlib
import json
import os
from pathlib import Path

from httpx2 import ASGITransport, AsyncClient

from app.main import app

OPENAPI_CONTRACT_SHA256 = (
    "2917a2273b50c34343740a67605547f119318c50d27394d79e3890da8106c062"
)


def _compute_canonical_hash() -> str:
    canonical_schema = json.dumps(
        app.openapi(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical_schema).hexdigest()


def _persist_new_hash(new_hash: str) -> None:
    """Rewrite OPENAPI_CONTRACT_SHA256 in this source file."""
    source = Path(__file__).read_text(encoding="utf-8")
    updated = source.replace(OPENAPI_CONTRACT_SHA256, new_hash)
    Path(__file__).write_text(updated, encoding="utf-8")


def test_openapi_schema_matches_reviewed_snapshot() -> None:
    """Require an explicit review for every public HTTP contract change."""
    new_hash = _compute_canonical_hash()

    if os.environ.get("UPDATE_OPENAPI_HASH"):
        _persist_new_hash(new_hash)
        return

    assert new_hash == OPENAPI_CONTRACT_SHA256


def test_openapi_metadata_and_operation_ids_are_stable() -> None:
    schema = app.openapi()

    assert schema["info"]["title"] == "Node Nexus API"
    assert schema["info"]["license"]["identifier"] == "MIT"
    assert schema["info"]["contact"]["name"] == "Node Nexus maintainers"

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert operation_ids
    assert len(operation_ids) == len(set(operation_ids))
    assert all(" " not in operation_id for operation_id in operation_ids)


def test_openapi_exposes_api_key_security_scheme() -> None:
    schema = app.openapi()

    scheme = schema["components"]["securitySchemes"]["APIKeyHeader"]
    assert scheme == {"type": "apiKey", "in": "header", "name": "X-API-Key"}


async def test_runtime_api_documentation_endpoints() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        openapi = await client.get("/openapi.json")
        swagger = await client.get("/docs")
        redoc = await client.get("/redoc")

    assert openapi.status_code == 200
    assert openapi.json()["info"]["title"] == "Node Nexus API"
    assert swagger.status_code == 200
    assert "swagger-ui" in swagger.text
    assert redoc.status_code == 200
    assert "redoc" in redoc.text.lower()
