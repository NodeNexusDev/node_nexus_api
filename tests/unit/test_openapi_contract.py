"""OpenAPI contract quality checks."""

import hashlib
import json

from httpx2 import ASGITransport, AsyncClient

from app.main import app

OPENAPI_CONTRACT_SHA256 = (
    "14e69f233719712499bf8c39145acffe0d69e8c0abd4f850a5a29de55ff08e91"
)


def test_openapi_schema_matches_reviewed_snapshot() -> None:
    """Require an explicit review for every public HTTP contract change."""
    canonical_schema = json.dumps(
        app.openapi(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()

    assert hashlib.sha256(canonical_schema).hexdigest() == OPENAPI_CONTRACT_SHA256


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
